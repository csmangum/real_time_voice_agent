import asyncio
import logging
import queue
import traceback

import aiohttp
import numpy as np
import pyaudio
from aiortc import RTCPeerConnection, RTCSessionDescription
from aiortc.mediastreams import MediaStreamError

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("WebRTC-Test-Client")


class AudioStreamPlayer:
    """Class to play received audio in real-time."""

    def __init__(self, track, buffer_size=4096):  # Larger buffer for stability
        self.track = track
        self.buffer_size = buffer_size
        # Jitter buffer implementation as a queue
        self.audio_queue = queue.Queue(
            maxsize=100
        )  # Larger queue to handle network jitter
        self.running = False
        self.sample_rate = 48000  # WebRTC default
        self.pyaudio_instance = pyaudio.PyAudio()
        self.stream = None
        self.prebuffer_count = 10  # Wait for this many frames before starting playback
        self.prebuffer_done = False

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

                    # Simple conversion to int16 with safety checks
                    try:
                        # Ensure the range is within [-1.0, 1.0] before scaling
                        max_val = max(abs(np.max(audio_data)), abs(np.min(audio_data)))
                        if max_val > 1.0:
                            audio_data = (
                                audio_data / max_val
                            )  # Normalize if outside range

                        # Convert to int16
                        pcm_data = (audio_data * 32767).astype(np.int16).tobytes()
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

                        # If buffer is getting too full, remove some frames to prevent buildup
                        if current_buffer_level > 0.9 * self.audio_queue.maxsize:
                            # Remove older frames to make room
                            frames_to_drop = int(
                                current_buffer_level * 0.2
                            )  # Drop 20% of frames
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
        """Stop playing audio."""
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

            logger.info("Stopped audio playback")


async def run_test_client(server_url="http://localhost:8000"):
    # Create peer connection
    pc = RTCPeerConnection()

    # Audio player
    audio_player = None

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

    @dc.on("open")
    def on_open():
        logger.info("✓ Data channel opened")
        # Send a test message to the server
        dc.send("Hello from test client!")
        logger.info("Sent test message to server")

    @dc.on("message")
    def on_message(message):
        logger.info(f"Received data: {message}")

    @dc.on("close")
    def on_close():
        logger.info("Data channel closed")

    # Track connection state for debugging
    @pc.on("connectionstatechange")
    async def on_connectionstatechange():
        logger.info(f"Connection state changed to: {pc.connectionState}")
        if pc.connectionState == "failed" or pc.connectionState == "closed":
            logger.error(f"Connection state is {pc.connectionState}!")
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
                    await pc.close()
                    return
    except Exception as e:
        logger.error(f"Error communicating with server: {e}")
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
        await pc.close()
        return

    # Keep connection open until stop event is set or timeout
    try:
        logger.info("Connection established, waiting for audio stream...")
        print("Listening for audio... Press Ctrl+C to stop.")

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

        logger.info("Closing connection")
        await pc.close()
        logger.info("Connection closed")


if __name__ == "__main__":
    asyncio.run(run_test_client())
