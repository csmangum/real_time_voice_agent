import asyncio
import fractions  # Added for Fraction
import os
import threading
import time
import wave
from argparse import ArgumentParser

import numpy as np
import pyaudio
import requests
from aiortc import (
    RTCConfiguration,
    RTCIceCandidate,
    RTCIceServer,
    RTCPeerConnection,
    RTCSessionDescription,
)
from aiortc.contrib.media import MediaStreamTrack


# Custom audio track using PyAudio for microphone capture
class PyAudioStreamTrack(MediaStreamTrack):
    kind = "audio"

    def __init__(
        self, sample_rate=16000, channels=1, frame_size=480, save_local_recording=True
    ):
        super().__init__()
        self.sample_rate = sample_rate
        self.channels = channels
        self.frame_size = frame_size
        self._timestamp = 0
        self._start_time = None
        self.frames = []  # Store audio frames
        self.total_bytes = 0
        self.audio_buffer = asyncio.Queue()  # Buffer for audio data
        self.last_error_time = 0  # To prevent spamming error messages
        self.save_local_recording = (
            save_local_recording  # Option to save recording locally
        )

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

        # Initialize recording flag but don't start yet
        self.recording = False
        self.record_task = None

    def start_recording(self):
        """Start the audio recording process"""
        if not self.recording:
            self.recording = True
            self.record_task = asyncio.create_task(self._record_audio())
            print("Audio recording started")

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

                    # Add to buffer for recv() to use
                    await self.audio_buffer.put(data)

                    # Log progress (less frequently to avoid console spam)
                    if len(self.frames) % 100 == 0:
                        seconds = len(self.frames) * self.frame_size / self.sample_rate
                        print(
                            f"Recorded {len(self.frames)} frames ({seconds:.1f} sec, {self.total_bytes/1024:.1f} KB)"
                        )
                except Exception as e:
                    # Rate limit error messages
                    current_time = time.time()
                    if (
                        current_time - self.last_error_time > 5
                    ):  # Only log every 5 seconds
                        print(f"Error reading from stream: {e}")
                        self.last_error_time = current_time

                # Small sleep to avoid blocking
                await asyncio.sleep(0.001)
        except Exception as e:
            print(f"Recording task error: {e}")

    async def recv(self):
        import av

        if self._start_time is None:
            self._start_time = time.time()

        # Get audio data from the buffer instead of reading from device again
        try:
            # Use a timeout to avoid blocking forever if stream stops
            data = await asyncio.wait_for(self.audio_buffer.get(), timeout=0.5)

            # Create audio frame directly
            frame = av.AudioFrame(
                format="s16",
                layout="mono" if self.channels == 1 else "stereo",
                samples=self.frame_size // self.channels,
            )
            frame.planes[0].update(data)

            # Update frame properties
            frame.rate = self.sample_rate
            frame.time_base = fractions.Fraction(1, self.sample_rate)
            frame.pts = self._timestamp
            self._timestamp += self.frame_size

            return frame

        except asyncio.TimeoutError:
            # Timeout waiting for audio data
            current_time = time.time()
            if current_time - self.last_error_time > 5:
                print("Timeout waiting for audio data")
                self.last_error_time = current_time

            # Create silent frame
            import av

            frame = av.AudioFrame(
                format="s16",
                layout="mono" if self.channels == 1 else "stereo",
                samples=self.frame_size // self.channels,
            )
            # Fill with silence (zeros)
            frame.planes[0].update(b"\x00" * (self.frame_size * 2))
            frame.rate = self.sample_rate
            frame.time_base = fractions.Fraction(1, self.sample_rate)
            frame.pts = self._timestamp
            self._timestamp += self.frame_size
            return frame

        except Exception as e:
            # Only log errors occasionally to prevent flooding
            current_time = time.time()
            if current_time - self.last_error_time > 5:
                print(f"Error in recv: {e}")
                self.last_error_time = current_time

            # Create empty frame if there's an error
            import av

            frame = av.AudioFrame(
                format="s16",
                layout="mono" if self.channels == 1 else "stereo",
                samples=self.frame_size // self.channels,
            )
            # Fill with silence (zeros)
            frame.planes[0].update(b"\x00" * (self.frame_size * 2))
            frame.rate = self.sample_rate
            frame.time_base = fractions.Fraction(1, self.sample_rate)
            frame.pts = self._timestamp
            self._timestamp += self.frame_size
            return frame

    def stop(self):
        # Stop recording task
        self.recording = False
        
        # Only try to save frames if we actually recorded something
        if self.record_task and self.frames and self.save_local_recording:
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
        elif not self.save_local_recording:
            print("Local recording disabled - no client-side file saved")
        elif not self.frames:
            print("No audio frames captured - recording may never have started")
        else:
            print("No audio frames captured!")

        if self.stream:
            self.stream.stop_stream()
            self.stream.close()
        if self.p:
            self.p.terminate()
        print("PyAudio stream closed")

    async def drain_buffers(self, timeout=2.0):
        """Wait for all buffered audio to be sent"""
        print(f"Draining audio buffers for up to {timeout} seconds...")
        start_time = time.time()
        while not self.audio_buffer.empty() and time.time() - start_time < timeout:
            await asyncio.sleep(0.1)
        print(f"Buffer drain completed after {time.time() - start_time:.2f} seconds")
        return


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


async def run_client(server_url, max_duration=60, save_local_recording=True, sample_rate=16000):
    # Wait for user to press Enter before starting
    await wait_for_enter()

    print(f"Starting WebRTC audio streaming to {server_url}")
    print(
        f"Will automatically stop after {max_duration} seconds (or press Ctrl+C to stop earlier)"
    )
    if save_local_recording:
        print("Client-side recording enabled - will save audio locally")
    else:
        print("Client-side recording disabled - relying on server recording only")

    # Create optimized peer connection configuration
    config = RTCConfiguration(
        iceServers=[
            RTCIceServer(
                urls=["stun:stun.l.google.com:19302", "stun:stun1.l.google.com:19302"]
            )
        ]
    )
    pc = RTCPeerConnection(config)

    # Create variable to store client ID
    client_id = None

    # Store ICE candidates that are generated before we get the client ID
    pending_ice_candidates = []

    # Set up connection state change handler
    @pc.on("connectionstatechange")
    async def on_connectionstatechange():
        print(f"Connection state changed to: {pc.connectionState}")
        if pc.connectionState == "failed":
            print("Connection failed - may need to restart client")
        elif pc.connectionState == "connected":
            print("Successfully connected to the server")
            # Start recording when connection is established
            audio_track.start_recording()
            print("Audio recording started now that connection is established")

    # Set up ICE candidate handler
    @pc.on("icecandidate")
    async def on_icecandidate(candidate):
        nonlocal client_id, pending_ice_candidates
        if candidate:
            print(
                f"Generated ICE candidate: {candidate.sdpMid}:{candidate.sdpMLineIndex}"
            )

            if client_id:
                # Send the ICE candidate to the server
                await send_ice_candidate(candidate, client_id, server_url)
            else:
                # Store the candidate for later sending
                print("No client ID yet, storing ICE candidate for later")
                pending_ice_candidates.append(candidate)

    # Set up data channel for potential messaging
    @pc.on("datachannel")
    def on_datachannel(channel):
        @channel.on("message")
        def on_message(message):
            print(f"Received message from server: {message}")

    # Create a stop event for graceful shutdown
    stop_event = asyncio.Event()

    # Create audio track from microphone with optimized parameters
    audio_track = PyAudioStreamTrack(
        sample_rate=sample_rate, 
        frame_size=480,  # Reduced frame size for lower latency
        save_local_recording=save_local_recording
    )
    
    # Add track with high priority for better latency
    pc.addTrack(audio_track)

    # Create offer
    offer = await pc.createOffer()
    
    # Log SDP for debugging WebRTC audio formats
    sdp_lines = offer.sdp.split('\n')
    print("Analyzing WebRTC SDP offer for audio format:")
    audio_lines = [line for line in sdp_lines if "a=rtpmap:109" in line or "opus" in line]
    for line in audio_lines:
        print(f"  SDP: {line}")
    
    await pc.setLocalDescription(offer)

    # Send offer to server
    try:
        print(f"Connecting to server at {server_url}...")
        print("Sending WebRTC offer to server...")

        # Add audio format information to the request
        audio_format = {
            "sample_rate": sample_rate,
            "channels": audio_track.channels,
            "sample_width": 2,  # 2 bytes for 'int16'
            "format": "s16"
        }
        
        print(f"Sending audio format info to server: {audio_format}")
        print("Note: WebRTC may resample/convert this audio during transmission")
        
        try:
            response = requests.post(
                f"{server_url}/offer",
                json={
                    "sdp": pc.localDescription.sdp, 
                    "type": pc.localDescription.type,
                    "audio_format": audio_format  # Include format parameters
                },
                timeout=5,  # Add timeout to prevent hanging indefinitely
            )
            response.raise_for_status()
            answer_data = response.json()

            # Check if the server included a clientId in the response
            if "clientId" in answer_data:
                client_id = answer_data["clientId"]
                print(f"Received client ID from server: {client_id}")

                # Now send any pending ICE candidates
                if pending_ice_candidates:
                    print(
                        f"Sending {len(pending_ice_candidates)} pending ICE candidates"
                    )
                    for candidate in pending_ice_candidates:
                        await send_ice_candidate(candidate, client_id, server_url)
                    # Clear the pending candidates
                    pending_ice_candidates = []
            else:
                print("Warning: Server did not provide a client ID")

            # Set remote description
            await pc.setRemoteDescription(
                RTCSessionDescription(sdp=answer_data["sdp"], type=answer_data["type"])
            )

            print("WebRTC connection established. Streaming audio...")
            print("Press Ctrl+C to stop")
        except requests.exceptions.ConnectionError as e:
            print(f"Could not connect to server: {e}")
            print(
                "Is the server running? Check that the server is running at the specified URL."
            )
            print(
                "Continuing to record audio locally even though server connection failed..."
            )
            # We don't return here so we can still record locally

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

            # Print connection state periodically
            if int(time.time()) % 10 == 0:  # Every 10 seconds
                print(f"Current connection state: {pc.connectionState}")

            await asyncio.sleep(1)

    except KeyboardInterrupt:
        print("Keyboard interrupt received")
    except Exception as e:
        print(f"Error: {e}")
    finally:
        # Cleanup
        print("Closing connection...")
        
        # Add graceful shutdown with delay to ensure all audio is transmitted
        print("Waiting for all audio to be transmitted (3 seconds)...")
        # First stop recording but don't close stream yet
        if audio_track.recording:
            audio_track.recording = False
            if audio_track.record_task:
                try:
                    # Wait for recording task to finish
                    await asyncio.wait_for(audio_track.record_task, timeout=1.0)
                except asyncio.TimeoutError:
                    print("Timeout waiting for recording task to finish")
                
            # Wait for any buffered audio to be sent
            await audio_track.drain_buffers(timeout=2.0)
            
            # Add additional delay to ensure server processing
            # Increased from 2.0 to 3.0 to match server-side delay
            await asyncio.sleep(3.0)
            print("Graceful shutdown delay completed")
        
        # Now fully stop the audio track
        audio_track.stop()

        # Ensure proper connection closure
        if pc.connectionState != "closed":
            print(f"Closing connection (current state: {pc.connectionState})")
            await pc.close()

            # Wait a moment for the close to propagate
            await asyncio.sleep(2)

        print("Connection closed")


# Helper function to send ICE candidates to server
async def send_ice_candidate(candidate, client_id, server_url):
    try:
        ice_data = {
            "candidate": candidate.candidate,
            "sdpMid": candidate.sdpMid,
            "sdpMLineIndex": candidate.sdpMLineIndex,
            "clientId": client_id,
        }

        print(f"Sending ICE candidate to server for client ID: {client_id}")
        ice_response = requests.post(
            f"{server_url}/ice-candidate", json=ice_data, timeout=5
        )

        if ice_response.status_code == 200:
            print("ICE candidate sent successfully")
        else:
            print(f"Failed to send ICE candidate: {ice_response.status_code}")
    except Exception as e:
        print(f"Error sending ICE candidate to server: {e}")


if __name__ == "__main__":
    parser = ArgumentParser()
    parser.add_argument(
        "--server", type=str, default="http://localhost:8000", help="Server URL"
    )
    parser.add_argument(
        "--duration", type=int, default=60, help="Maximum recording duration in seconds"
    )
    parser.add_argument(
        "--no-save-local",
        action="store_true",
        help="Disable audio recording on client side",
    )
    parser.add_argument(
        "--sample-rate",
        type=int,
        default=16000,
        help="Audio sample rate (default: 16000, reduced from 48000 for lower latency)",
    )
    args = parser.parse_args()

    # Run the client
    try:
        asyncio.run(run_client(args.server, args.duration, not args.no_save_local, args.sample_rate))
    except KeyboardInterrupt:
        print("Program terminated by user")
