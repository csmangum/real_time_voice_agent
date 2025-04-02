import asyncio
import os
import time
import uuid
import wave
from contextlib import asynccontextmanager
from typing import Dict, List, Optional

import av
import numpy as np
import uvicorn
from aiortc import (
    MediaStreamTrack,
    RTCIceCandidate,
    RTCPeerConnection,
    RTCSessionDescription,
)
from aiortc.contrib.media import MediaRecorder
from aiortc.mediastreams import MediaStreamError
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel


# Define lifespan context manager
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: nothing specific needed here
    yield
    # Shutdown: close all connections
    print("Application shutting down - cleaning up connections")
    # Close all peer connections and stop all recorders
    tasks = [cleanup(client_id) for client_id in list(pcs.keys())]
    await asyncio.gather(*tasks)
    print("All recorders stopped and connections closed")

    # Check if any recordings were created
    if os.path.exists("recordings"):
        files = os.listdir("recordings")
        print(f"Recording directory contains {len(files)} files: {files}")


# Create FastAPI app with lifespan
app = FastAPI(lifespan=lifespan)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Store active peer connections and recorders
pcs: Dict[str, RTCPeerConnection] = {}
recorders: Dict[str, MediaRecorder] = {}
audio_frames: Dict[str, List[bytes]] = {}
audio_formats: Dict[str, Dict] = {}  # Store format info for each client
client_cleanup_lock: Dict[str, bool] = {}  # Track if cleanup is in progress
client_last_activity: Dict[str, float] = {}  # Track when we last received data
client_start_times: Dict[str, float] = {}  # Track when each client started recording
client_session_info: Dict[str, Dict] = {}  # Additional session information

# Constants for audio processing
MAX_BACKFILL_GAP = 10  # Maximum number of frames to backfill for small gaps
FRAME_INTERPOLATION = True  # Whether to use interpolation for missing frames


# Audio processing class
class AudioTrackProcessor(MediaStreamTrack):
    kind = "audio"

    def __init__(self, track, client_id):
        super().__init__()
        self.track = track
        self.client_id = client_id
        self.frame_count = 0
        self.sample_rate = 48000  # Default, will be updated from frame
        self.channels = 1  # Default, will be updated from frame
        self.sample_width = 2  # Default (16-bit), will be updated from frame
        self.format_detected = False

        # Add frame loss tracking
        self.missed_frames = 0
        self.total_expected_frames = 0
        self.last_pts = None
        self.first_pts = None
        self.last_timestamp = time.time()

        # Create a buffer for potentially missed frames
        self.last_valid_frame = None
        self.frame_buffer = []  # Store recent frames for interpolation
        self.max_buffer_size = 20  # Number of recent frames to keep

    async def recv(self):
        try:
            frame = await self.track.recv()
            current_time = time.time()
            time_since_last = current_time - self.last_timestamp
            self.last_timestamp = current_time
            self.frame_count += 1

            # Record the first PTS for timing information
            if self.first_pts is None and hasattr(frame, "pts"):
                self.first_pts = frame.pts
                if self.client_id in client_session_info:
                    client_session_info[self.client_id]["first_pts"] = self.first_pts
                    client_session_info[self.client_id][
                        "first_frame_time"
                    ] = current_time

            # Track frame timestamps to detect gaps
            if self.last_pts is not None and hasattr(frame, "pts"):
                # Calculate expected frames based on time elapsed and sample rate
                expected_pts_diff = frame.samples  # Typically matches the frame size
                actual_pts_diff = frame.pts - self.last_pts

                # Detect unusually large gaps that indicate packet loss
                if (
                    actual_pts_diff > expected_pts_diff * 1.2
                ):  # Be more aggressive about detecting gaps
                    # Gap detected
                    missed_frames = int(
                        (actual_pts_diff - expected_pts_diff) / expected_pts_diff
                    )
                    time_gap = time_since_last

                    # Don't count extremely large gaps as those are likely just PTS resets
                    if missed_frames < 1000:  # Reasonable maximum for a gap
                        self.missed_frames += missed_frames
                        self.total_expected_frames += missed_frames
                        print(
                            f"Detected gap of ~{missed_frames} frames between PTS {self.last_pts} and {frame.pts} (time gap: {time_gap:.3f}s)"
                        )

                        # Only try to fill smaller gaps - large gaps would create too much artificial audio
                        if (
                            missed_frames <= MAX_BACKFILL_GAP
                            and self.last_valid_frame is not None
                            and self.client_id in audio_frames
                        ):
                            # Use interpolation if enabled and we have enough frames in our buffer
                            if FRAME_INTERPOLATION and len(self.frame_buffer) >= 2:
                                # Create interpolated frames to fill the gap
                                print(
                                    f"Interpolating {missed_frames} frames to fill the gap"
                                )
                                for i in range(missed_frames):
                                    # Simple linear interpolation between frames
                                    # For more complex audio, more sophisticated interpolation would be needed
                                    position = (i + 1) / (
                                        missed_frames + 1
                                    )  # Relative position in the gap
                                    try:
                                        # Use the last two frames as reference points
                                        last_frame_data = self._extract_audio_data(
                                            self.frame_buffer[-1]
                                        )
                                        prev_frame_data = self._extract_audio_data(
                                            self.frame_buffer[-2]
                                        )

                                        if (
                                            last_frame_data
                                            and prev_frame_data
                                            and len(last_frame_data)
                                            == len(prev_frame_data)
                                        ):
                                            # Linear interpolation between the two frames
                                            interp_frame = bytearray(
                                                len(last_frame_data)
                                            )
                                            for j in range(
                                                0, len(last_frame_data), 2
                                            ):  # 2 bytes per sample for 16-bit
                                                if j + 1 < len(last_frame_data):
                                                    # Get samples from both frames as integers
                                                    prev_sample = int.from_bytes(
                                                        prev_frame_data[j : j + 2],
                                                        byteorder="little",
                                                        signed=True,
                                                    )
                                                    last_sample = int.from_bytes(
                                                        last_frame_data[j : j + 2],
                                                        byteorder="little",
                                                        signed=True,
                                                    )
                                                    # Interpolate
                                                    interp_sample = int(
                                                        prev_sample * (1 - position)
                                                        + last_sample * position
                                                    )
                                                    # Convert back to bytes
                                                    interp_frame[j : j + 2] = (
                                                        interp_sample.to_bytes(
                                                            2,
                                                            byteorder="little",
                                                            signed=True,
                                                        )
                                                    )

                                            audio_frames[self.client_id].append(
                                                bytes(interp_frame)
                                            )
                                    except Exception as e:
                                        print(
                                            f"Interpolation error: {e} - falling back to duplicating frames"
                                        )
                                        # If interpolation fails, fall back to duplicating the last frame
                                        fill_data = self._extract_audio_data(
                                            self.last_valid_frame
                                        )
                                        if fill_data:
                                            audio_frames[self.client_id].append(
                                                fill_data
                                            )
                            else:
                                # Extract data from the last valid frame
                                fill_data = self._extract_audio_data(
                                    self.last_valid_frame
                                )
                                if fill_data:
                                    # Add it for each missed frame (up to the limit)
                                    fill_count = min(missed_frames, MAX_BACKFILL_GAP)
                                    for _ in range(fill_count):
                                        audio_frames[self.client_id].append(fill_data)

                                    print(
                                        f"Added {fill_count} fill frames to compensate for gap"
                                    )

            if hasattr(frame, "pts"):
                self.last_pts = frame.pts
            self.total_expected_frames += 1

            # Update client activity timestamp
            client_last_activity[self.client_id] = time.time()

            # Update format information if available
            if not self.format_detected:
                if hasattr(frame, "rate") and frame.rate is not None:
                    self.sample_rate = frame.rate

                if hasattr(frame, "layout"):
                    # Handle layout as string or object
                    layout_str = str(frame.layout)
                    self.channels = 2 if "stereo" in layout_str else 1

                if hasattr(frame, "format"):
                    # Map PyAV format to byte width
                    format_to_width = {
                        "s16": 2,  # 16-bit
                        "s32": 4,  # 32-bit
                        "flt": 4,  # float
                        "dbl": 8,  # double
                        "u8": 1,  # 8-bit unsigned
                        "s8": 1,  # 8-bit signed
                    }
                    if frame.format in format_to_width:
                        self.sample_width = format_to_width[frame.format]

                # Store format info for this client
                audio_formats[self.client_id] = {
                    "sample_rate": self.sample_rate,
                    "channels": self.channels,
                    "sample_width": self.sample_width,
                    "format": getattr(frame, "format", "unknown"),
                }

                print(
                    f"Audio format for client {self.client_id}: {audio_formats[self.client_id]}"
                )
                self.format_detected = True

            # Convert frame to bytes and store
            if self.client_id in audio_frames:
                # Extract audio data using the most appropriate method
                pcm_bytes = self._extract_audio_data(frame)

                if pcm_bytes:
                    # Add to main recording buffer
                    audio_frames[self.client_id].append(pcm_bytes)

                    # Update the frame buffer for future interpolation
                    self.frame_buffer.append(frame)
                    # Keep buffer size limited
                    if len(self.frame_buffer) > self.max_buffer_size:
                        self.frame_buffer.pop(0)

                    self.last_valid_frame = (
                        frame  # Store this frame for potential gap filling
                    )

                    # Log occasionally to avoid flooding
                    if self.frame_count % 100 == 0:
                        total_kb = (
                            sum(len(b) for b in audio_frames[self.client_id]) / 1024
                        )
                        audio_sec = (
                            len(audio_frames[self.client_id])
                            * len(pcm_bytes)
                            / (self.sample_width * self.channels * self.sample_rate)
                        )
                        loss_percent = (
                            self.missed_frames / max(1, self.total_expected_frames)
                        ) * 100
                        print(
                            f"Processed {self.frame_count} frames for client {self.client_id} - Total: {total_kb:.1f} KB ({audio_sec:.1f} sec)"
                        )
                        print(
                            f"Estimated frame loss: {self.missed_frames}/{self.total_expected_frames} frames ({loss_percent:.1f}%)"
                        )
                        # Calculate real-time elapsed since first frame
                        if (
                            self.first_pts is not None
                            and "first_frame_time"
                            in client_session_info.get(self.client_id, {})
                        ):
                            elapsed_real = (
                                time.time()
                                - client_session_info[self.client_id][
                                    "first_frame_time"
                                ]
                            )
                            print(
                                f"Real time elapsed: {elapsed_real:.1f}s vs recorded time: {audio_sec:.1f}s (ratio: {audio_sec/elapsed_real:.2f})"
                            )
                elif self.frame_count % 100 == 0:
                    print(
                        f"Warning: Could not extract audio data from frame {self.frame_count}"
                    )

            return frame

        except MediaStreamError:
            print(
                f"MediaStreamError: Track ended for client {self.client_id} - this is normal when connection ends"
            )

            # Let the track.on("ended") handler handle the cleanup
            # to avoid race conditions with duplicate cleanup attempts
            print(f"Leaving cleanup to the track.on('ended') handler...")

            # Re-raise to signal track end to aiortc internals
            raise

        except asyncio.CancelledError:
            print(
                f"Track processing cancelled for client {self.client_id} - normal during shutdown"
            )
            raise

        except ConnectionResetError:
            print(
                f"Connection reset for client {self.client_id} - client likely disconnected"
            )
            raise

        except Exception as e:
            import traceback

            error_details = (
                str(e) if str(e) else "Empty error message - likely track ended"
            )
            print(f"Error in recv for client {self.client_id}: {error_details}")
            print(f"Error type: {type(e).__name__}")
            print(f"Traceback: {traceback.format_exc()}")
            # Re-raise to ensure proper error handling
            raise

    def _extract_audio_data(self, frame) -> Optional[bytes]:
        """Extract audio data from frame using the most reliable method available"""
        try:
            # Method 1: Use PyAV's to_ndarray if available (most accurate)
            if hasattr(frame, "to_ndarray"):
                try:
                    array = frame.to_ndarray()
                    return array.tobytes()
                except Exception as e:
                    print(f"to_ndarray failed: {e}")

            # Method 2: Access plane data directly
            if hasattr(frame, "planes") and len(frame.planes) > 0:
                try:
                    return bytes(frame.planes[0])
                except Exception as e:
                    print(f"Plane extraction failed: {e}")

            # Method 3: For backwards compatibility
            if hasattr(frame, "to_bytes"):
                try:
                    return frame.to_bytes()
                except Exception as e:
                    print(f"to_bytes failed: {e}")

            # Method 4: Direct buffer access for specific frame types
            if hasattr(frame, "buffer") and frame.buffer:
                try:
                    return bytes(frame.buffer)
                except Exception as e:
                    print(f"Buffer extraction failed: {e}")

            # Method 5: Create a placeholder silent frame if everything else fails
            if hasattr(frame, "samples") and hasattr(frame, "format"):
                try:
                    # Create silence with the same properties as the frame
                    bytes_per_sample = 2  # Default for s16
                    if frame.format == "s32" or frame.format == "flt":
                        bytes_per_sample = 4
                    elif frame.format == "dbl":
                        bytes_per_sample = 8

                    channels = 1
                    if hasattr(frame, "layout") and "stereo" in str(frame.layout):
                        channels = 2

                    # Create silent frame with correct size
                    silence = b"\x00" * (frame.samples * channels * bytes_per_sample)
                    print(f"Created placeholder silent frame ({len(silence)} bytes)")
                    return silence
                except Exception as e:
                    print(f"Silence creation failed: {e}")

            return None
        except Exception as e:
            print(f"Audio extraction error: {e}")
            return None


class OfferModel(BaseModel):
    sdp: str
    type: str


class IceCandidateModel(BaseModel):
    candidate: str
    sdpMLineIndex: int
    sdpMid: str
    clientId: str


@app.get("/", response_class=HTMLResponse)
async def index():
    with open("templates/index.html", "r") as f:
        return f.read()


@app.post("/offer")
async def offer(params: OfferModel):
    offer = RTCSessionDescription(sdp=params.sdp, type=params.type)

    pc = RTCPeerConnection()
    client_id = str(uuid.uuid4())
    pcs[client_id] = pc
    client_cleanup_lock[client_id] = False  # Initialize cleanup lock
    client_last_activity[client_id] = time.time()  # Set initial activity time
    client_start_times[client_id] = time.time()  # Record when this client started

    # Initialize session info
    client_session_info[client_id] = {
        "start_time": time.time(),
        "first_frame_time": None,
        "first_pts": None,
        "sdp_offer": params.sdp,  # Store original SDP for debugging
    }

    # Prepare audio file path
    os.makedirs("recordings", exist_ok=True)
    timestamp = time.strftime("%Y%m%d-%H%M%S")
    audio_file = f"recordings/audio_{timestamp}_{client_id[-8:]}.wav"

    # Initialize frame storage and format info
    audio_frames[client_id] = []
    audio_formats[client_id] = {
        "sample_rate": 48000,
        "channels": 1,
        "sample_width": 2,
        "format": "s16",
    }

    # Store the audio file path for later use in cleanup
    audio_formats[client_id]["file_path"] = audio_file

    # Create recorder - but we'll use the raw data for the primary recording now
    recorder = MediaRecorder(audio_file)
    recorders[client_id] = recorder

    @pc.on("track")
    def on_track(track):
        print(f"Track received: {track.kind} from client {client_id}")
        if track.kind == "audio":
            local_track = AudioTrackProcessor(track, client_id)
            pc.addTrack(local_track)
            recorder.addTrack(local_track)
            print(f"Added audio track to recorder for client {client_id}")

        @track.on("ended")
        async def on_ended():
            print(f"Track ended for client {client_id}")
            # Explicitly save audio on track end
            try:
                # Use a small delay to allow any pending frames to be processed
                await asyncio.sleep(0.5)

                if client_id in pcs:  # Only cleanup if client still exists
                    # Check if we have enough audio frames to save
                    if client_id in audio_frames and len(audio_frames[client_id]) > 0:
                        frames_count = len(audio_frames[client_id])
                        print(
                            f"Track ended with {frames_count} audio frames available for saving"
                        )
                        await cleanup(client_id)
                    else:
                        print(
                            f"Track ended but no audio frames available for client {client_id}"
                        )
                        await cleanup(client_id)
            except Exception as e:
                import traceback

                print(f"Error in track.ended handler: {e}")
                print(f"Error type: {type(e).__name__}")
                print(f"Traceback: {traceback.format_exc()}")

    @pc.on("icecandidate")
    def on_icecandidate(candidate):
        print(
            f"ICE candidate generated for client {client_id}: {candidate and candidate.sdpMid}"
        )
        # In a full solution, these would be sent to the client
        # This is handled by the WebRTC internals for now

    @pc.on("connectionstatechange")
    async def on_connectionstatechange():
        state = pc.connectionState
        print(f"Connection state for {client_id}: {state}")

        if state == "connected":
            print(f"Client {client_id} successfully connected")
        elif state in ["failed", "closed"]:
            print(f"Client {client_id} connection {state}, cleaning up")
            if client_id in pcs:  # Only cleanup if client still exists
                await cleanup(client_id)
        elif state == "disconnected":
            print(f"Client {client_id} temporarily disconnected")
            # Start a task to check if it reconnects within a timeout
            asyncio.create_task(check_reconnect(client_id, timeout=10))

    # Set the remote description
    await pc.setRemoteDescription(offer)
    await recorder.start()
    print(f"Recorder started for client {client_id}, writing to {audio_file}")

    # Create answer
    answer = await pc.createAnswer()
    await pc.setLocalDescription(answer)

    # Start inactivity checker task
    asyncio.create_task(check_client_activity(client_id))

    return {
        "sdp": pc.localDescription.sdp,
        "type": pc.localDescription.type,
        "clientId": client_id,
    }


@app.post("/ice-candidate")
async def handle_ice_candidate(params: IceCandidateModel):
    client_id = params.clientId

    if client_id not in pcs:
        return {"status": "error", "message": "Client not found"}

    pc = pcs[client_id]

    # Create and add ICE candidate
    candidate = RTCIceCandidate(
        component=None,
        foundation=None,
        ip=None,
        port=None,
        priority=None,
        protocol=None,
        type=None,
        sdpMid=params.sdpMid,
        sdpMLineIndex=params.sdpMLineIndex,
        candidate=params.candidate,
    )

    await pc.addIceCandidate(candidate)
    print(f"Added ICE candidate for client {client_id}")

    return {"status": "success"}


async def check_reconnect(client_id, timeout):
    """Wait for a client to reconnect before cleaning up"""
    try:
        if client_id not in pcs:
            return

        # Wait for the timeout period
        for _ in range(timeout):
            await asyncio.sleep(1)
            # Check if client has reconnected
            if client_id in pcs and pcs[client_id].connectionState == "connected":
                print(f"Client {client_id} successfully reconnected")
                return
            # Check if client is already cleaned up
            if client_id not in pcs:
                print(f"Client {client_id} already cleaned up during reconnection wait")
                return

        # After timeout, check if client is still disconnected
        if client_id in pcs and pcs[client_id].connectionState in [
            "disconnected",
            "failed",
        ]:
            print(
                f"Client {client_id} failed to reconnect after {timeout}s, cleaning up"
            )
            await cleanup(client_id)
    except Exception as e:
        import traceback

        print(f"Error in reconnect checker for {client_id}: {e}")
        print(f"Error type: {type(e).__name__}")
        print(f"Traceback: {traceback.format_exc()}")


async def check_client_activity(client_id, max_inactivity=30):
    """Monitor client for inactivity and clean up if necessary"""
    try:
        while client_id in pcs and client_id in client_last_activity:
            # Calculate inactivity time
            inactivity_time = time.time() - client_last_activity[client_id]

            # If client has been inactive too long, clean up
            if inactivity_time > max_inactivity:
                print(
                    f"Client {client_id} inactive for {inactivity_time:.1f}s, closing connection"
                )
                await cleanup(client_id)
                break

            # Check every 5 seconds
            await asyncio.sleep(5)
    except Exception as e:
        print(f"Error in activity checker for {client_id}: {e}")


async def cleanup(client_id):
    # Prevent duplicate cleanups
    if client_id not in pcs or client_cleanup_lock.get(client_id, False):
        return

    # Mark this client as being cleaned up
    client_cleanup_lock[client_id] = True
    print(f"Starting cleanup for client {client_id}")

    try:
        pc = pcs[client_id]

        # Stop recorder if exists
        if client_id in recorders:
            recorder = recorders[client_id]
            audio_file = audio_formats.get(client_id, {}).get("file_path", None)
            print(f"Stopping recorder for client {client_id}")

            try:
                await asyncio.wait_for(recorder.stop(), timeout=3.0)
                print(f"Recorder stopped successfully")
            except asyncio.TimeoutError:
                print(f"Timeout stopping recorder - continuing with cleanup")
            except MediaStreamError:
                print(
                    f"MediaStreamError during recorder stop - this is normal when the track ends"
                )
            except Exception as e:
                print(f"Error stopping recorder: {e}")

            # Remove the recorder from our tracking dict
            if client_id in recorders:
                del recorders[client_id]

            # Create our own high-quality recording from raw frames
            if client_id in audio_frames and audio_frames[client_id]:
                try:
                    # Check if we have start time info to compare with client
                    start_time = client_start_times.get(client_id)
                    duration = time.time() - start_time if start_time else None

                    # Generate new timestamp for the better quality recording
                    timestamp = time.strftime("%Y%m%d-%H%M%S")
                    main_path = f"recordings/main_{timestamp}_{client_id[-8:]}.wav"
                    frames = audio_frames[client_id]

                    # Calculate duration based on frames
                    format_info = audio_formats.get(
                        client_id,
                        {"sample_rate": 48000, "channels": 1, "sample_width": 2},
                    )
                    sample_rate = format_info.get("sample_rate", 48000)
                    frame_size = len(frames[0]) if frames else 0
                    bytes_per_sample = format_info.get("sample_width", 2)
                    channels = format_info.get("channels", 1)

                    # Calculate samples per frame
                    samples_per_frame = (
                        frame_size / (bytes_per_sample * channels) if frame_size else 0
                    )

                    # Expected duration based on audio data
                    frame_count = len(frames)
                    audio_duration = (frame_count * samples_per_frame) / sample_rate

                    print(
                        f"Audio stats: {frame_count} frames, {samples_per_frame} samples/frame"
                    )
                    print(
                        f"Session duration: {duration:.1f}s, audio duration: {audio_duration:.1f}s"
                    )

                    # Determine if we're missing audio at the end based on session vs audio duration
                    if (
                        duration and audio_duration < duration * 0.95
                    ):  # More than 5% shorter
                        missing_seconds = duration - audio_duration
                        print(
                            f"Audio appears to be {missing_seconds:.1f}s shorter than the session - adding compensation"
                        )

                        # Add compensation silence at the end
                        if frame_size > 0:
                            missing_frames = int(
                                (missing_seconds * sample_rate) / samples_per_frame
                            )
                            print(
                                f"Adding {missing_frames} silence frames ({missing_seconds:.1f}s) to match session duration"
                            )
                            for _ in range(missing_frames):
                                frames.append(b"\x00" * frame_size)

                    # Add a short amount of silence at the end to prevent abrupt cutoffs
                    # Get a representative frame to determine format
                    if frames:
                        frame_size = len(frames[0])
                        # Add 0.5 seconds of silence at the end in all cases
                        silence_size = int(
                            0.5 * sample_rate * channels * bytes_per_sample
                        )
                        silence_frames = silence_size // frame_size + 1

                        print(
                            f"Adding {silence_frames} frames of silence ({silence_size} bytes) at the end of recording"
                        )
                        for _ in range(silence_frames):
                            frames.append(b"\x00" * frame_size)

                    total_size = sum(len(frame) for frame in frames)
                    final_duration = (len(frames) * samples_per_frame) / sample_rate

                    print(
                        f"Saving primary recording with {len(frames)} frames ({total_size/1024:.1f} KB) to {main_path}"
                    )
                    print(f"Using format: {format_info}")
                    print(
                        f"Final audio duration: {final_duration:.1f}s ({100*final_duration/duration:.1f}% of session duration)"
                    )

                    # Normalize frame lengths - ensure all frames have the same size
                    # This fixes potential audio corruption if frame sizes vary
                    if frames:
                        # Find the most common frame size
                        frame_sizes = [len(f) for f in frames]
                        most_common_size = max(set(frame_sizes), key=frame_sizes.count)

                        # Normalize frames to the most common size
                        normalized_frames = []
                        for frame in frames:
                            if len(frame) == most_common_size:
                                normalized_frames.append(frame)
                            elif len(frame) < most_common_size:
                                # Pad shorter frames with silence
                                padding = b"\x00" * (most_common_size - len(frame))
                                normalized_frames.append(frame + padding)
                            else:
                                # Truncate longer frames
                                normalized_frames.append(frame[:most_common_size])

                        print(
                            f"Normalized {len(frames)} frames to consistent size of {most_common_size} bytes"
                        )
                        frames = normalized_frames

                    # Write raw audio to wav file with detected format
                    with wave.open(main_path, "wb") as wf:
                        wf.setnchannels(format_info["channels"])
                        wf.setsampwidth(format_info["sample_width"])
                        wf.setframerate(format_info["sample_rate"])
                        wf.writeframes(b"".join(frames))

                    file_size = os.path.getsize(main_path)
                    print(
                        f"Primary audio saved to {main_path} ({file_size/1024:.1f} KB)"
                    )

                    # Only create fallback if original MediaRecorder fails
                    main_recorder_successful = (
                        audio_file
                        and os.path.exists(audio_file)
                        and os.path.getsize(audio_file) > 1000
                    )

                    if not main_recorder_successful:
                        print(
                            f"Original MediaRecorder recording failed, keeping the new recording as primary"
                        )
                    else:
                        print(
                            f"Both recordings successful - compare to see which has better quality"
                        )

                except Exception as e:
                    import traceback

                    print(f"Error saving primary audio: {e}")
                    print(f"Error type: {type(e).__name__}")
                    print(f"Traceback: {traceback.format_exc()}")
            else:
                print(f"No frames to save for client {client_id}")

            # Clean up audio frames and format info
            if client_id in audio_frames:
                del audio_frames[client_id]
            if client_id in audio_formats:
                del audio_formats[client_id]
            if client_id in client_last_activity:
                del client_last_activity[client_id]
            if client_id in client_start_times:
                del client_start_times[client_id]
            if client_id in client_session_info:
                del client_session_info[client_id]

        # Close peer connection
        await pc.close()

        # Delete the peer connection from dictionaries
        if client_id in pcs:
            del pcs[client_id]

        if client_id in client_cleanup_lock:
            del client_cleanup_lock[client_id]

        print(f"Cleanup completed for client {client_id}")

    except Exception as e:
        import traceback

        print(f"Error during cleanup for {client_id}: {e}")
        print(f"Error type: {type(e).__name__}")
        print(f"Traceback: {traceback.format_exc()}")


if __name__ == "__main__":
    # Create templates directory if it doesn't exist
    os.makedirs("templates", exist_ok=True)

    # Create a simple HTML file for testing
    with open("templates/index.html", "w") as f:
        f.write(
            """
        <!DOCTYPE html>
        <html>
        <head>
            <title>WebRTC Audio Streaming</title>
        </head>
        <body>
            <h1>WebRTC Audio Streaming</h1>
            <button id="startButton">Start Streaming</button>
            <button id="stopButton" disabled>Stop Streaming</button>
            
            <script>
                const startButton = document.getElementById('startButton');
                const stopButton = document.getElementById('stopButton');
                
                let pc;
                let clientId;
                
                startButton.addEventListener('click', async () => {
                    startButton.disabled = true;
                    
                    // Create peer connection with STUN servers
                    pc = new RTCPeerConnection({
                        iceServers: [
                            { urls: ['stun:stun.l.google.com:19302', 'stun:stun1.l.google.com:19302'] }
                        ]
                    });
                    
                    // Set up ICE candidate handling
                    pc.onicecandidate = async (event) => {
                        if (event.candidate && clientId) {
                            console.log('Sending ICE candidate to server');
                            try {
                                await fetch('/ice-candidate', {
                                    method: 'POST',
                                    headers: {
                                        'Content-Type': 'application/json'
                                    },
                                    body: JSON.stringify({
                                        candidate: event.candidate.candidate,
                                        sdpMid: event.candidate.sdpMid,
                                        sdpMLineIndex: event.candidate.sdpMLineIndex,
                                        clientId: clientId
                                    })
                                });
                            } catch (e) {
                                console.error('Error sending ICE candidate:', e);
                            }
                        }
                    };
                    
                    try {
                        const stream = await navigator.mediaDevices.getUserMedia({ audio: true, video: false });
                        stream.getTracks().forEach(track => pc.addTrack(track, stream));
                        
                        pc.oniceconnectionstatechange = () => {
                            console.log('ICE connection state:', pc.iceConnectionState);
                        };
                        
                        pc.onconnectionstatechange = () => {
                            console.log('Connection state:', pc.connectionState);
                            if (pc.connectionState === 'connected') {
                                console.log('Successfully connected to server');
                            }
                        };
                        
                        const offer = await pc.createOffer();
                        await pc.setLocalDescription(offer);
                        
                        const response = await fetch('/offer', {
                            method: 'POST',
                            headers: {
                                'Content-Type': 'application/json'
                            },
                            body: JSON.stringify({
                                sdp: pc.localDescription.sdp,
                                type: pc.localDescription.type
                            })
                        });
                        
                        const answer = await response.json();
                        clientId = answer.clientId;  // Store client ID for ICE candidates
                        
                        await pc.setRemoteDescription({
                            type: answer.type,
                            sdp: answer.sdp
                        });
                        
                        stopButton.disabled = false;
                    } catch (e) {
                        console.error('Error:', e);
                        startButton.disabled = false;
                    }
                });
                
                stopButton.addEventListener('click', () => {
                    if (pc) {
                        pc.close();
                        pc = null;
                    }
                    
                    startButton.disabled = false;
                    stopButton.disabled = true;
                });
            </script>
        </body>
        </html>
        """
        )

    uvicorn.run(app, host="0.0.0.0", port=8000)
