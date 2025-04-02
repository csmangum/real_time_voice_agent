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
MAX_BACKFILL_GAP = 3  # Reduced from 10 to 3 - Maximum number of frames to backfill for small gaps
FRAME_INTERPOLATION = False  # Disabled frame interpolation to reduce processing overhead


# Audio processing class
class AudioTrackProcessor(MediaStreamTrack):
    kind = "audio"

    def __init__(self, track, client_id):
        super().__init__()
        self.track = track
        self.client_id = client_id
        self.frame_count = 0
        
        # Initially use client-provided format but always verify with actual frame data
        if client_id in audio_formats:
            format_info = audio_formats[client_id]
            self.sample_rate = format_info.get("sample_rate")
            self.channels = format_info.get("channels", 1)
            self.sample_width = format_info.get("sample_width", 2)
            # We consider format as NOT detected - we'll verify from actual frames
            self.format_detected = False
            print(f"Starting with client-provided format for {client_id}: {format_info} (will verify)")
        else:
            # Otherwise start with no format until detected
            self.sample_rate = None
            self.channels = 1
            self.sample_width = 2
            self.format_detected = False

        # Add frame loss tracking
        self.missed_frames = 0
        self.total_expected_frames = 0
        self.last_pts = None
        self.first_pts = None
        self.last_timestamp = time.time()

        # Create a buffer for potentially missed frames
        self.last_valid_frame = None
        self.max_buffer_size = 20  # Number of recent frames to keep

        print(f"Created AudioTrackProcessor for client {client_id}")

    # Update format detection to be more robust
    def _detect_and_update_format(self, frame):
        format_changed = False
        initial_detection = not self.format_detected
        
        # Try to detect sample rate from frame - this is crucial for correct playback speed
        if hasattr(frame, "rate") and frame.rate is not None:
            if self.sample_rate != frame.rate:
                print(f"Detected sample rate: {frame.rate}Hz for client {self.client_id} (was: {self.sample_rate}Hz)")
                self.sample_rate = frame.rate
                format_changed = True
        
        # Detect channel layout
        if hasattr(frame, "layout"):
            layout_str = str(frame.layout)
            channels = 2 if "stereo" in layout_str else 1
            if self.channels != channels:
                print(f"Detected {channels} channels for client {self.client_id} (was: {self.channels})")
                self.channels = channels
                format_changed = True

        # Detect sample format and width
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
                new_width = format_to_width[frame.format]
                if self.sample_width != new_width:
                    print(f"Detected {frame.format} format ({new_width} bytes) for client {self.client_id} (was: {self.sample_width})")
                    self.sample_width = new_width
                    format_changed = True
        
        # If we detected any format change or this is initial detection, always update audio_formats
        if (format_changed or initial_detection) and self.sample_rate is not None:
            # Update the actual detected format
            detected_format = {
                "sample_rate": self.sample_rate,
                "channels": self.channels,
                "sample_width": self.sample_width,
                "format": getattr(frame, "format", "unknown"),
                "detected": True,  # Mark this as a detected format
            }
            
            # Save client-provided values for reference
            if self.client_id in audio_formats and audio_formats[self.client_id].get("client_provided", False):
                detected_format["original_client_rate"] = audio_formats[self.client_id].get("sample_rate")
                detected_format["original_client_channels"] = audio_formats[self.client_id].get("channels")
                detected_format["client_provided"] = True
            
            # Retain file path if it was already set
            if self.client_id in audio_formats and "file_path" in audio_formats[self.client_id]:
                detected_format["file_path"] = audio_formats[self.client_id]["file_path"]
            
            # Update the global format info
            audio_formats[self.client_id] = detected_format
            
            # Format was successfully detected
            self.format_detected = True
            
            # Log the update
            if format_changed:
                print(f"Updated audio format for client {self.client_id}: {detected_format}")
                if initial_detection:
                    print(f"Initial format detection complete")
                else:
                    print(f"Format change detected at frame {self.frame_count}")
            return True
            
        return False

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
                    client_session_info[self.client_id]["first_frame_time"] = current_time
                    # Calculate initial latency
                    initial_latency = (current_time - client_session_info[self.client_id].get("connection_timestamp", current_time)) * 1000
                    print(f"First audio frame latency: {initial_latency:.2f}ms for client {self.client_id}")

            # Track frame timestamps for minimal gap detection
            if self.last_pts is not None and hasattr(frame, "pts"):
                # Simplified gap detection with less overhead
                expected_pts_diff = frame.samples
                actual_pts_diff = frame.pts - self.last_pts

                # Only detect significant gaps to reduce overhead
                if actual_pts_diff > expected_pts_diff * 2:
                    self.missed_frames += int((actual_pts_diff - expected_pts_diff) / expected_pts_diff)
                    # Only log major gap issues
                    if self.frame_count % 100 == 0 or actual_pts_diff > expected_pts_diff * 5:
                        print(f"Detected significant gap between PTS {self.last_pts} and {frame.pts}")

            if hasattr(frame, "pts"):
                self.last_pts = frame.pts
            self.total_expected_frames += 1

            # Update client activity timestamp
            client_last_activity[self.client_id] = time.time()

            # Always check the format for the first 10 frames to ensure accurate detection
            if self.frame_count <= 10:
                self._detect_and_update_format(frame)
            # Then check occasionally for any changes (WebRTC can change format mid-stream)
            elif self.frame_count % 100 == 0:
                self._detect_and_update_format(frame)

            # Optimize audio extraction for faster handling
            if self.client_id in audio_frames:
                # Fast path direct plane access
                try:
                    if hasattr(frame, "planes") and len(frame.planes) > 0:
                        pcm_bytes = bytes(frame.planes[0])
                    else:
                        pcm_bytes = self._extract_audio_data(frame)
                        
                    if pcm_bytes:
                        # Add to main recording buffer
                        audio_frames[self.client_id].append(pcm_bytes)
                        self.last_valid_frame = frame
                        
                        # Reduced logging frequency
                        if self.frame_count % 500 == 0:
                            total_kb = sum(len(b) for b in audio_frames[self.client_id]) / 1024
                            audio_sec = len(audio_frames[self.client_id]) * len(pcm_bytes) / (self.sample_width * self.channels * self.sample_rate or 48000)
                            print(f"Processed {self.frame_count} frames ({total_kb:.1f} KB, {audio_sec:.1f} sec) for client {self.client_id}")
                except Exception as e:
                    if self.frame_count % 500 == 0:  # Reduced error logging
                        print(f"Frame processing error: {str(e)}")

            return frame

        except MediaStreamError:
            print(f"MediaStreamError: Track ended for client {self.client_id}")
            raise
        except asyncio.CancelledError:
            print(f"Track processing cancelled for client {self.client_id}")
            raise
        except Exception as e:
            print(f"Error in recv for client {self.client_id}: {str(e)}")
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
    audio_format: dict = None  # Optional dict for audio format parameters


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

    # Log connection start with timestamp for latency tracking
    start_timestamp = time.time()
    print(f"Connection request received at {start_timestamp:.6f} for client {client_id}")

    # Initialize session info
    client_session_info[client_id] = {
        "start_time": time.time(),
        "first_frame_time": None,
        "first_pts": None,
        "sdp_offer": params.sdp,  # Store original SDP for debugging
        "connection_timestamp": start_timestamp,
    }

    # Prepare audio file path
    os.makedirs("recordings", exist_ok=True)
    timestamp = time.strftime("%Y%m%d-%H%M%S")
    audio_file = f"recordings/audio_{timestamp}_{client_id[-8:]}.wav"

    # Initialize frame storage and format info
    audio_frames[client_id] = []
    
    # Use client-provided format if available, otherwise use defaults
    if params.audio_format:
        audio_formats[client_id] = params.audio_format
        audio_formats[client_id]["client_provided"] = True  # Mark as explicitly provided
        print(f"Using client-provided audio format: {params.audio_format}")
    else:
        audio_formats[client_id] = {
            "sample_rate": 48000,
            "channels": 1,
            "sample_width": 2,
            "format": "s16",
            "client_provided": False  # Mark as default
        }
        print(f"Client didn't provide format, using defaults: {audio_formats[client_id]}")

    # Store the audio file path for later use in cleanup
    audio_formats[client_id]["file_path"] = audio_file

    # Create recorder - but we'll use the raw data for the primary recording now
    recorder = MediaRecorder(audio_file)
    recorders[client_id] = recorder

    @pc.on("track")
    def on_track(track):
        track_receive_time = time.time()
        print(f"Track received: {track.kind} from client {client_id} at {track_receive_time:.6f}")
        print(f"Track latency: {(track_receive_time - start_timestamp)*1000:.2f}ms")
        
        if track.kind == "audio":
            local_track = AudioTrackProcessor(track, client_id)
            
            # Add track with high priority for latency optimization
            pc.addTrack(local_track)
            recorder.addTrack(local_track)
            print(f"Added audio track to recorder for client {client_id} with high priority")

        @track.on("ended")
        async def on_ended():
            print(f"Track ended for client {client_id}")
            # Explicitly save audio on track end
            try:
                # Add a longer delay to allow all pending frames to be processed
                print(f"Waiting for additional audio frames to arrive (3 seconds)...")
                await asyncio.sleep(3.0)

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
            # Add delay before cleanup to ensure all frames are processed
            print(f"Waiting for final audio frames to be processed (3 seconds)...")
            await asyncio.sleep(3.0)
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

                    # Ensure format info is set with correct values
                    if client_id in audio_formats:
                        format_info = audio_formats[client_id]
                    else:
                        format_info = {"sample_rate": 48000, "channels": 1, "sample_width": 2}
                    
                    # Get format parameters from detected values
                    sample_rate = format_info.get("sample_rate", 48000)
                    if sample_rate is None or sample_rate <= 0:
                        print(f"Warning: Invalid sample rate detected: {sample_rate}, using 16000Hz")
                        sample_rate = 16000
                        
                    channels = format_info.get("channels", 1)
                    if channels <= 0:
                        channels = 1
                        
                    bytes_per_sample = format_info.get("sample_width", 2)
                    if bytes_per_sample <= 0:
                        bytes_per_sample = 2
                    
                    # Log where format came from
                    format_source = "detected from frames"
                    if format_info.get("detected", False):
                        format_source = "detected from actual audio frames"
                    elif format_info.get("client_provided", False):
                        format_source = "explicitly provided by client but overridden"
                    
                    print(f"Creating WAV with format: {sample_rate}Hz, {channels} channels, {bytes_per_sample} bytes per sample")
                    print(f"Format was {format_source}")
                    
                    # If we have both client-provided and detected formats that differ, show the difference
                    if format_info.get("client_provided", False) and format_info.get("detected", False):
                        original_rate = format_info.get("original_client_rate")
                        if original_rate and original_rate != sample_rate:
                            print(f"WebRTC changed sample rate: client sent {original_rate}Hz but WebRTC delivered {sample_rate}Hz")
                        
                        original_channels = format_info.get("original_client_channels")
                        if original_channels and original_channels != channels:
                            print(f"WebRTC changed channels: client sent {original_channels} but WebRTC delivered {channels}")
                    
                    # Calculate frame size (bytes)
                    frame_size = len(frames[0]) if frames else 0
                    
                    # Calculate samples per frame
                    samples_per_frame = (
                        frame_size / (bytes_per_sample * channels) if frame_size and bytes_per_sample and channels else 0
                    )

                    # Expected duration based on audio data
                    frame_count = len(frames)
                    audio_duration = (frame_count * samples_per_frame) / sample_rate if sample_rate > 0 else 0
                    
                    # Get the actual session duration for comparison
                    if client_id in client_start_times:
                        actual_duration = time.time() - client_start_times[client_id]
                        print(f"Session actual duration: {actual_duration:.1f}s vs calculated audio duration: {audio_duration:.1f}s")
                        
                        # Check for significant timing mismatch (more than 20% difference)
                        if actual_duration > 0 and abs(actual_duration - audio_duration) / actual_duration > 0.2:
                            print(f"WARNING: Significant timing mismatch detected! Received audio is {audio_duration/actual_duration*100:.1f}% of real-time duration")
                            
                            # Check if this is likely due to WebRTC resampling
                            webrtc_resampled = False
                            if format_info.get("client_provided", False) and format_info.get("detected", False):
                                original_rate = format_info.get("original_client_rate")
                                if original_rate and original_rate != sample_rate:
                                    ratio = sample_rate / original_rate
                                    expected_ratio = actual_duration / audio_duration
                                    # If the ratios are close, it's likely just WebRTC resampling
                                    if abs(ratio - expected_ratio) / expected_ratio < 0.1:
                                        print(f"Timing mismatch explained by WebRTC resampling: {original_rate}Hz → {sample_rate}Hz")
                                        webrtc_resampled = True
                            
                            if not webrtc_resampled:
                                print(f"This may indicate timing or buffering issues between client and server")
                                
                                # Calculate correction factor for sample rate
                                if audio_duration > 0 and actual_duration > 0:
                                    correction_factor = actual_duration / audio_duration
                                    # Only apply correction if it's significant but not extreme
                                    if 0.5 < correction_factor < 5.0:
                                        corrected_sample_rate = int(sample_rate * correction_factor)
                                        print(f"Applying sample rate correction: {sample_rate}Hz -> {corrected_sample_rate}Hz (factor: {correction_factor:.2f})")
                                        sample_rate = corrected_sample_rate
                                    else:
                                        print(f"Correction factor too extreme ({correction_factor:.2f}), not applying. Check client/server sync.")

                    print(
                        f"Audio stats: {frame_count} frames, {samples_per_frame} samples/frame"
                    )
                    print(
                        f"Session duration: {duration:.1f}s, audio duration: {audio_duration:.1f}s"
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
                        wf.setnchannels(channels)
                        wf.setsampwidth(bytes_per_sample)
                        wf.setframerate(sample_rate)  # This is crucial for correct playback speed
                        wf.writeframes(b"".join(frames))

                    file_size = os.path.getsize(main_path)
                    print(
                        f"Primary audio saved to {main_path} ({file_size/1024:.1f} KB), {audio_duration:.1f}s at {sample_rate}Hz"
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
                
                stopButton.addEventListener('click', async () => {
                    if (pc) {
                        console.log('Gracefully stopping connection...');
                        stopButton.disabled = true;
                        stopButton.textContent = 'Stopping...';
                        
                        // Add a short delay to ensure all audio gets transmitted
                        await new Promise(resolve => {
                            setTimeout(() => {
                                console.log('Graceful shutdown delay complete');
                                resolve();
                            }, 3000);
                        });
                        
                        // Now close the connection
                        pc.close();
                        pc = null;
                        console.log('Connection closed');
                    }
                    
                    startButton.disabled = false;
                    stopButton.disabled = true;
                    stopButton.textContent = 'Stop Streaming';
                });
            </script>
        </body>
        </html>
        """
        )

    uvicorn.run(app, host="0.0.0.0", port=8000)
