import asyncio
import fractions  # Add this import for Fraction
import logging
import os
import queue
import time
import traceback
import wave
from datetime import datetime

import aiohttp
import numpy as np
import pyaudio
from aiortc import RTCPeerConnection, RTCSessionDescription
from aiortc.mediastreams import AudioStreamTrack, MediaStreamError

# Set up logging
# Ensure logs directory exists
os.makedirs("logs", exist_ok=True)

# Create a unique log filename with timestamp
log_filename = f"logs/client_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

# Set up logging to both console and file
logger = logging.getLogger("WebRTC-Test-Client")
logger.setLevel(logging.INFO)

# Create console handler
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)

# Create file handler
file_handler = logging.FileHandler(log_filename, encoding="utf-8")
file_handler.setLevel(logging.INFO)

# Create formatter and add it to the handlers
formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
console_handler.setFormatter(formatter)
file_handler.setFormatter(formatter)

# Add handlers to logger
logger.addHandler(console_handler)
logger.addHandler(file_handler)

logger.info(f"Logging to file: {log_filename}")

# Ensure recordings directory exists
os.makedirs("client_recordings", exist_ok=True)


class AudioStreamPlayer:
    """Class to play received audio in real-time and optionally record it."""

    def __init__(self, track, buffer_size=2048):  # Smaller buffer for less latency
        self.track = track
        self.buffer_size = buffer_size
        # Jitter buffer implementation as a queue
        self.audio_queue = queue.Queue(maxsize=20)  # Smaller queue to reduce latency
        self.running = False
        self.sample_rate = 48000  # WebRTC default
        self.pyaudio_instance = pyaudio.PyAudio()
        self.stream = None
        self.prebuffer_count = 3  # Fewer frames to reduce initial delay
        self.prebuffer_done = False

        # Recording variables
        self.should_record = True
        self.recording_filename = (
            f"client_recordings/server_audio_{int(time.time())}.wav"
        )
        self.wav_file = None
        self.all_audio_data = bytearray()

    def audio_callback(self, in_data, frame_count, time_info, status):
        """PyAudio callback to fetch and play audio data"""
        # If pre-buffering is not complete, return silence
        if not self.prebuffer_done:
            return (b"\x00" * frame_count * 2, pyaudio.paContinue)

        try:
            # Try to get data from the queue
            data = self.audio_queue.get_nowait()
            # Check if data size matches expected size (2 bytes per sample)
            expected_size = frame_count * 2
            if len(data) < expected_size:
                # Pad with zeros if too short
                data = data + b"\x00" * (expected_size - len(data))
            elif len(data) > expected_size:
                # Truncate if too long
                data = data[:expected_size]
            return (data, pyaudio.paContinue)
        except queue.Empty:
            # If queue is empty, return silence
            return (b"\x00" * frame_count * 2, pyaudio.paContinue)

    async def start(self):
        """Start playing audio from the track."""
        self.running = True

        # Start PyAudio stream
        self.stream = self.pyaudio_instance.open(
            format=pyaudio.paInt16,
            channels=1,
            rate=self.sample_rate,
            output=True,
            frames_per_buffer=self.buffer_size,
            stream_callback=self.audio_callback,
        )

        # Start the stream, but it won't play yet due to prebuffering
        self.stream.start_stream()
        logger.info("Started audio stream (prebuffering...)")

        # Initialize WAV file for recording if recording is enabled
        if self.should_record:
            try:
                logger.info(f"Recording server audio to {self.recording_filename}")
                self.wav_file = wave.open(self.recording_filename, "wb")
                self.wav_file.setnchannels(1)  # Mono
                self.wav_file.setsampwidth(2)  # 16-bit
                self.wav_file.setframerate(self.sample_rate)  # 48kHz
            except Exception as e:
                logger.error(f"Error creating WAV file: {e}")
                self.should_record = False

        # Start the worker to receive frames
        self.worker_task = asyncio.create_task(self._receive_frames())

    async def _receive_frames(self):
        """Worker to receive frames from the track and add them to the queue."""
        prebuffer_frames = 0

        try:
            while self.running:
                try:
                    frame = await self.track.recv()

                    # Get audio data and ensure it's in the correct format
                    audio_data = frame.to_ndarray()

                    # Improved conversion to int16 with proper normalization
                    try:
                        # Check if audio data is already in reasonable range
                        max_val = np.max(np.abs(audio_data))

                        # Normalize only if needed (if max amplitude is too low or too high)
                        if max_val > 1.0 or max_val < 0.1:
                            # Normalize to appropriate range for good volume
                            audio_data = audio_data / max_val * 0.8

                        # Apply a small gain boost if volume is too low
                        if max_val < 0.3:
                            audio_data = audio_data * 1.5

                        # Consider adding a simple limiter to avoid clipping
                        audio_data = np.clip(audio_data, -0.95, 0.95)

                        # Convert to int16 with proper scaling
                        pcm_data = (audio_data * 32767).astype(np.int16).tobytes()

                        # Save the audio data if recording is enabled
                        if self.should_record and self.wav_file:
                            self.all_audio_data.extend(pcm_data)
                    except Exception as e:
                        logger.error(f"Error converting audio data: {e}")
                        continue  # Skip this frame if conversion fails

                    # Prebuffering stage
                    if not self.prebuffer_done:
                        self.audio_queue.put(
                            pcm_data
                        )  # Use blocking put during prebuffer
                        prebuffer_frames += 1

                        if prebuffer_frames >= self.prebuffer_count:
                            self.prebuffer_done = True
                            logger.info(
                                f"Prebuffering complete ({prebuffer_frames} frames). Starting playback."
                            )
                    else:
                        # Regular operation - try to maintain a consistent buffer level
                        current_buffer_level = self.audio_queue.qsize()

                        # If buffer is getting too full, remove some frames to maintain low latency
                        if current_buffer_level > 0.8 * self.audio_queue.maxsize:
                            # Remove older frames to make room
                            frames_to_drop = int(
                                current_buffer_level * 0.3
                            )  # Drop 30% of frames if backed up
                            for _ in range(frames_to_drop):
                                try:
                                    self.audio_queue.get_nowait()
                                except queue.Empty:
                                    break

                        # Add the current frame
                        try:
                            self.audio_queue.put_nowait(pcm_data)
                        except queue.Full:
                            # If still full, drop oldest frame
                            self.audio_queue.get_nowait()
                            self.audio_queue.put_nowait(pcm_data)

                except MediaStreamError:
                    logger.warning("Media stream error, stopping playback")
                    break
        except Exception as e:
            logger.error(f"Error in receive_frames: {e}")
            logger.error(traceback.format_exc())
        finally:
            logger.info("Stopping frame receiver")

    async def stop(self):
        """Stop playing audio and save recording if enabled."""
        if self.running:
            self.running = False

            # Cancel the worker task
            if hasattr(self, "worker_task"):
                self.worker_task.cancel()
                try:
                    await self.worker_task
                except asyncio.CancelledError:
                    pass

            # Stop and close the PyAudio stream
            if self.stream:
                self.stream.stop_stream()
                self.stream.close()
                self.stream = None

            # Terminate PyAudio
            if self.pyaudio_instance:
                self.pyaudio_instance.terminate()
                self.pyaudio_instance = None

            # Finalize recording if enabled
            if self.should_record and self.wav_file:
                try:
                    # Write all collected audio data to the WAV file
                    if self.all_audio_data:
                        self.wav_file.writeframes(self.all_audio_data)
                    self.wav_file.close()
                    logger.info(f"Saved server audio to {self.recording_filename}")
                except Exception as e:
                    logger.error(f"Error saving audio recording: {e}")

            logger.info("Stopped audio playback")


class MicrophoneStreamTrack(AudioStreamTrack):
    """A track that captures audio from the microphone."""

    def __init__(self):
        super().__init__()
        self.sample_rate = 48000
        self.channels = 1
        self.sample_width = 2  # 16-bit
        self.running = False
        self.audio_queue = asyncio.Queue()
        # Thread-safe queue for PyAudio callback
        self.thread_queue = queue.Queue()
        self.pyaudio_instance = pyaudio.PyAudio()
        self.stream = None
        self._task = None
        # For timestamp tracking
        self._timestamp = 0
        self._samples_per_frame = 960  # 20ms at 48kHz
        # Add a flag to track if connection is active
        self.connection_active = True

    def audio_callback(self, in_data, frame_count, time_info, status):
        """PyAudio callback to capture microphone data"""
        if self.running and self.connection_active:
            # Only put data in queue if connection is still active
            self.thread_queue.put(in_data)
        return (None, pyaudio.paContinue)

    async def _transfer_audio_data(self):
        """Transfer audio data from thread queue to asyncio queue"""
        while self.running and self.connection_active:
            try:
                # Check if there's data in the thread queue
                if not self.thread_queue.empty():
                    # Get data from thread queue
                    data = self.thread_queue.get_nowait()
                    # Put data in asyncio queue
                    await self.audio_queue.put(data)
                else:
                    # Small sleep to prevent CPU spinning
                    await asyncio.sleep(0.001)
            except Exception as e:
                logger.error(f"Error transferring audio data: {e}")
                await asyncio.sleep(0.001)

    async def start(self):
        """Start capturing audio from the microphone."""
        self.running = True
        self.connection_active = True

        # Start PyAudio stream for microphone capture
        self.stream = self.pyaudio_instance.open(
            format=pyaudio.paInt16,
            channels=self.channels,
            rate=self.sample_rate,
            input=True,
            frames_per_buffer=self._samples_per_frame,  # 20ms at 48kHz
            stream_callback=self.audio_callback,
        )

        self.stream.start_stream()
        logger.info("Started microphone capture")

        # Start the task to transfer data from thread queue to asyncio queue
        self._task = asyncio.create_task(self._transfer_audio_data())

    def set_connection_inactive(self):
        """Mark the connection as inactive to stop sending data"""
        self.connection_active = False
        logger.info("Connection marked as inactive, stopping data sending")

    async def stop(self):
        """Stop capturing audio."""
        if self.running:
            self.running = False
            self.connection_active = False

            # Clear any remaining data in queues
            while not self.thread_queue.empty():
                try:
                    self.thread_queue.get_nowait()
                except:
                    pass

            while not self.audio_queue.empty():
                try:
                    await self.audio_queue.get()
                except:
                    pass

            # Cancel the transfer task
            if self._task:
                self._task.cancel()
                try:
                    await self._task
                except asyncio.CancelledError:
                    pass

            # Stop and close the PyAudio stream
            if self.stream:
                self.stream.stop_stream()
                self.stream.close()
                self.stream = None

            # Terminate PyAudio
            if self.pyaudio_instance:
                self.pyaudio_instance.terminate()
                self.pyaudio_instance = None

            logger.info("Stopped microphone capture")

    async def recv(self):
        """Get audio frame from the microphone."""
        try:
            if not self.running:
                await self.start()

            # Don't try to get audio data if connection is inactive
            if not self.connection_active:
                # Return empty audio frame when connection is inactive
                raise MediaStreamError("Connection is inactive")

            # Get audio data from the queue
            audio_data = await self.audio_queue.get()

            # Get timestamp (use parent class method)
            pts, time_base = await self._next_timestamp()

            # Create audio frame using the proper imported package
            from av import AudioFrame

            # Create frame from raw audio data - keep as signed 16-bit for Opus codec
            # Don't convert to float, keep as int16
            audio_array = np.frombuffer(audio_data, dtype=np.int16)

            # Create AudioFrame using the raw audio data as s16 format
            frame = AudioFrame(
                format="s16",
                layout="mono" if self.channels == 1 else "stereo",
                samples=len(audio_array) // self.channels,
            )

            # Set frame parameters
            frame.sample_rate = self.sample_rate
            frame.pts = pts
            frame.time_base = time_base

            # Copy the raw audio data to the frame's buffer
            frame.planes[0].update(audio_data)

            return frame
        except Exception as e:
            logger.error(f"Error in microphone track recv: {e}")
            logger.error(traceback.format_exc())
            # Signal that the track should stop
            if self.running:
                asyncio.create_task(self.stop())
            # Re-raise for proper error handling
            raise

    # Override the _next_timestamp method from AudioStreamTrack
    async def _next_timestamp(self):
        """Calculate timestamp for the next audio frame."""
        time_base = fractions.Fraction(
            1, self.sample_rate
        )  # Use Fraction instead of float
        pts = self._timestamp
        self._timestamp += self._samples_per_frame
        return pts, time_base


async def run_test_client(server_url="http://localhost:8000"):
    # Create peer connection
    pc = RTCPeerConnection()

    # Audio player
    audio_player = None
    mic_track = None

    # Signal for graceful shutdown
    stop_event = asyncio.Event()

    # Log ice candidates for debugging
    @pc.on("icecandidate")
    def on_icecandidate(candidate):
        logger.info(f"Generated ICE candidate: {candidate}")

    # Create a data channel
    logger.info("Creating data channel 'test-client-data'")
    dc = pc.createDataChannel("test-client-data")

    # Add an audio transceiver to receive audio from the server
    logger.info("Adding audio transceiver to receive audio from server")
    pc.addTransceiver("audio", direction="recvonly")

    # Create and add microphone track to send audio to server
    try:
        logger.info("Creating microphone track to send audio to server")
        mic_track = MicrophoneStreamTrack()
        await mic_track.start()
        pc.addTrack(mic_track)
        logger.info("Added microphone track to peer connection")
    except Exception as e:
        logger.error(f"Error setting up microphone track: {e}")
        logger.error(traceback.format_exc())

    @dc.on("open")
    def on_open():
        logger.info("[OK] Data channel opened")
        # Send a test message to the server
        dc.send("Hello from test client!")
        logger.info("Sent test message to server")

    @dc.on("message")
    def on_message(message):
        logger.info(f"Received data: {message}")

    @dc.on("close")
    def on_close():
        logger.info("Data channel closed")
        # Mark connection as inactive when data channel closes
        if mic_track:
            mic_track.set_connection_inactive()

    # Track connection state for debugging
    @pc.on("connectionstatechange")
    async def on_connectionstatechange():
        logger.info(f"Connection state changed to: {pc.connectionState}")
        if (
            pc.connectionState == "failed"
            or pc.connectionState == "closed"
            or pc.connectionState == "disconnected"
        ):
            logger.info(
                f"Connection state is {pc.connectionState}! Stopping data transmission."
            )
            # Mark connection as inactive immediately
            if mic_track:
                mic_track.set_connection_inactive()

            # Properly stop the microphone track
            if mic_track and mic_track.running:
                logger.info("Stopping microphone track due to connection state change")
                await mic_track.stop()

            # Set stop event to end the test client
            stop_event.set()

    # Handle audio tracks
    @pc.on("track")
    async def on_track(track):
        logger.info(f"Received track of kind: {track.kind}")
        if track.kind == "audio":
            nonlocal audio_player
            logger.info("Creating audio player for received track")
            audio_player = AudioStreamPlayer(track)
            await audio_player.start()

            @track.on("ended")
            async def on_ended():
                logger.info("Audio track ended")
                # Mark mic track connection as inactive when received track ends
                if mic_track:
                    mic_track.set_connection_inactive()
                if audio_player:
                    await audio_player.stop()
                stop_event.set()

    # Create an offer
    logger.info("Creating offer...")
    await pc.setLocalDescription(await pc.createOffer())
    logger.info("Local description set")

    # Send offer to server
    try:
        logger.info(f"Sending offer to {server_url}/offer")
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{server_url}/offer",
                json={"sdp": pc.localDescription.sdp, "type": pc.localDescription.type},
            ) as response:
                if response.status == 200:
                    answer_data = await response.json()
                    logger.info("Received answer from server")
                else:
                    error_text = await response.text()
                    logger.error(
                        f"Server returned error {response.status}: {error_text}"
                    )
                    # Ensure microphone is stopped even if server response fails
                    if mic_track and mic_track.running:
                        await mic_track.stop()
                    await pc.close()
                    return
    except Exception as e:
        logger.error(f"Error communicating with server: {e}")
        # Ensure microphone is stopped in case of error
        if mic_track and mic_track.running:
            await mic_track.stop()
        await pc.close()
        return

    # Set remote description
    try:
        logger.info("Setting remote description with answer from server")
        answer = RTCSessionDescription(sdp=answer_data["sdp"], type=answer_data["type"])
        await pc.setRemoteDescription(answer)
        logger.info("Remote description set successfully")
    except Exception as e:
        logger.error(f"Error setting remote description: {e}")
        # Ensure microphone is stopped in case of error
        if mic_track and mic_track.running:
            await mic_track.stop()
        await pc.close()
        return

    # Keep connection open until stop event is set or timeout
    try:
        logger.info("Connection established, waiting for audio stream...")
        print(
            "Listening for audio and sending microphone data... Press Ctrl+C to stop."
        )

        # Wait for the stop event or timeout after 60 seconds
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=60)
        except asyncio.TimeoutError:
            logger.info("Reached timeout, closing connection")

    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received")
    finally:
        # Clean up
        if audio_player:
            await audio_player.stop()

        # Ensure microphone is stopped properly
        if mic_track and mic_track.running:
            logger.info("Stopping microphone track in finally block")
            await mic_track.stop()

        logger.info("Closing connection")
        await pc.close()
        logger.info("Connection closed")


if __name__ == "__main__":
    asyncio.run(run_test_client())
