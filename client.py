import asyncio
import os
import time
import wave
import fractions  # Added for Fraction
from argparse import ArgumentParser

import numpy as np
import pyaudio
import requests
from aiortc import RTCPeerConnection, RTCSessionDescription
from aiortc.contrib.media import MediaStreamTrack


# Custom audio track using PyAudio for microphone capture
class PyAudioStreamTrack(MediaStreamTrack):
    kind = "audio"

    def __init__(self, sample_rate=48000, channels=1, frame_size=960):
        super().__init__()
        self.sample_rate = sample_rate
        self.channels = channels
        self.frame_size = frame_size
        self._timestamp = 0
        self._start_time = None
        self.frames = []  # Store audio frames
        self.total_bytes = 0

        # Create recordings directory if it doesn't exist
        os.makedirs("recordings", exist_ok=True)

        # Initialize PyAudio
        self.p = pyaudio.PyAudio()
        self.stream = self.p.open(
            format=pyaudio.paInt16,
            channels=channels,
            rate=sample_rate,
            input=True,
            frames_per_buffer=frame_size,
        )
        print(
            f"PyAudio stream opened for microphone capture: {sample_rate}Hz, {channels} channels, {frame_size} frame size"
        )

        # Start a separate task to capture audio directly
        self.recording = True
        self.record_task = asyncio.create_task(self._record_audio())

    async def _record_audio(self):
        """Continuously record audio in background"""
        try:
            while self.recording:
                # Read directly from the stream and store
                try:
                    data = self.stream.read(
                        self.frame_size, exception_on_overflow=False
                    )
                    self.frames.append(data)
                    self.total_bytes += len(data)

                    # Log progress
                    if len(self.frames) % 100 == 0:
                        seconds = len(self.frames) * self.frame_size / self.sample_rate
                        print(
                            f"Recorded {len(self.frames)} frames ({seconds:.1f} sec, {self.total_bytes/1024:.1f} KB)"
                        )
                except Exception as e:
                    print(f"Error reading from stream: {e}")

                # Small sleep to avoid blocking
                await asyncio.sleep(0.001)
        except Exception as e:
            print(f"Recording task error: {e}")

    async def recv(self):
        import av

        if self._start_time is None:
            self._start_time = time.time()

        # Read audio data from PyAudio
        try:
            data = self.stream.read(self.frame_size, exception_on_overflow=False)

            # Convert bytes to numpy array first
            array = np.frombuffer(data, dtype=np.int16)

            # Create audio frame directly without reshaping
            frame = av.AudioFrame(
                samples=self.frame_size // self.channels,
                format="s16",
                layout="mono" if self.channels == 1 else "stereo",
            )
            frame.planes[0].update(data)

            # Update frame properties
            frame.rate = self.sample_rate
            frame.time_base = fractions.Fraction(1, self.sample_rate)
            frame.pts = self._timestamp
            self._timestamp += self.frame_size

            return frame

        except Exception as e:
            print(f"Error in recv: {e}")
            # Create empty frame if there's an error
            frame = av.AudioFrame(
                samples=self.frame_size // self.channels,
                layout="mono" if self.channels == 1 else "stereo",
            )
            frame.rate = self.sample_rate
            frame.time_base = fractions.Fraction(1, self.sample_rate)
            frame.pts = self._timestamp
            self._timestamp += self.frame_size
            return frame

    def stop(self):
        # Stop recording task
        self.recording = False

        # Save the collected audio to a WAV file
        if self.frames:
            client_id = time.strftime("%Y%m%d-%H%M%S")
            filename = f"recordings/client_audio_{client_id}.wav"

            try:
                print(
                    f"Saving audio recording with {len(self.frames)} frames ({self.total_bytes/1024:.1f} KB)"
                )
                with wave.open(filename, "wb") as wf:
                    wf.setnchannels(self.channels)
                    wf.setsampwidth(2)  # 2 bytes for 'int16'
                    wf.setframerate(self.sample_rate)
                    wf.writeframes(b"".join(self.frames))

                file_size = os.path.getsize(filename)
                duration = len(self.frames) * self.frame_size / self.sample_rate
                print(
                    f"Audio saved to {filename} ({file_size/1024:.1f} KB, {duration:.1f} seconds)"
                )

                # List files in recordings directory
                files = os.listdir("recordings")
                print(f"Recording directory contains {len(files)} files:")
                for file in files:
                    file_path = os.path.join("recordings", file)
                    file_size = os.path.getsize(file_path)
                    print(f"- {file}: {file_size/1024:.1f} KB")
            except Exception as e:
                print(f"Error saving audio: {e}")
        else:
            print("No audio frames captured!")

        if self.stream:
            self.stream.stop_stream()
            self.stream.close()
        if self.p:
            self.p.terminate()
        print("PyAudio stream closed")


async def wait_for_enter():
    """Wait for the user to press Enter"""
    print("Press Enter to start streaming audio (Ctrl+C to exit)...")

    # Create an event to signal when Enter is pressed
    event = asyncio.Event()

    # Set up a task to read from stdin
    def stdin_callback():
        input()  # This will block until Enter is pressed
        event.set()

    # Run the blocking input() in a separate thread
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, stdin_callback)

    # Wait for the event to be set
    await event.wait()
    print("Starting audio streaming...")


async def run_client(server_url, max_duration=60):
    # Wait for user to press Enter before starting
    await wait_for_enter()

    print(f"Starting WebRTC audio streaming to {server_url}")
    print(
        f"Will automatically stop after {max_duration} seconds (or press Ctrl+C to stop earlier)"
    )

    # Create peer connection
    pc = RTCPeerConnection()

    # Create a stop event for graceful shutdown
    stop_event = asyncio.Event()

    # Create audio track from microphone
    audio_track = PyAudioStreamTrack()
    pc.addTrack(audio_track)

    # Create offer
    offer = await pc.createOffer()
    await pc.setLocalDescription(offer)

    # Send offer to server
    try:
        print(f"Connecting to server at {server_url}...")
        response = requests.post(
            f"{server_url}/offer",
            json={"sdp": pc.localDescription.sdp, "type": pc.localDescription.type},
        )
        response.raise_for_status()
        answer = response.json()

        # Set remote description
        await pc.setRemoteDescription(
            RTCSessionDescription(sdp=answer["sdp"], type=answer["type"])
        )

        print("WebRTC connection established. Streaming audio...")
        print("Press Ctrl+C to stop")

        # Setup timeout for max duration
        start_time = time.time()

        # Keep the connection alive until stop event or timeout
        while not stop_event.is_set():
            # Check if we've reached max duration
            if time.time() - start_time > max_duration:
                print(
                    f"Maximum duration of {max_duration} seconds reached, stopping..."
                )
                break

            await asyncio.sleep(1)

    except KeyboardInterrupt:
        print("Keyboard interrupt received")
    except Exception as e:
        print(f"Error: {e}")
    finally:
        # Cleanup
        print("Closing connection...")
        audio_track.stop()

        # Ensure proper connection closure
        if pc.connectionState != "closed":
            print(f"Closing connection (current state: {pc.connectionState})")
            await pc.close()

            # Wait a moment for the close to propagate
            await asyncio.sleep(2)

        print("Connection closed")


if __name__ == "__main__":
    parser = ArgumentParser()
    parser.add_argument(
        "--server", type=str, default="http://localhost:8000", help="Server URL"
    )
    parser.add_argument(
        "--duration", type=int, default=60, help="Maximum recording duration in seconds"
    )
    args = parser.parse_args()

    # Run the client
    try:
        asyncio.run(run_client(args.server, args.duration))
    except KeyboardInterrupt:
        print("Program terminated by user")
