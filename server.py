import asyncio
import socket
import json
import threading
import os
import wave
import time
import numpy as np
from aiortc import RTCPeerConnection, RTCSessionDescription, MediaStreamTrack
from aiortc.contrib.media import MediaRecorder, MediaBlackhole, MediaRelay
from av import AudioFrame

SIGNALING_PORT = 9999
RECORD_SECONDS = 10  # Match client recording time
DEFAULT_RECORDING_PATH = os.path.abspath("server_received.wav")  # Default path
TEMP_PATH = os.path.abspath("temp_recording.wav")  # Temporary file
DIRECT_RECORD_PATH = os.path.abspath("direct_recording.wav")  # Direct recording path

class DirectAudioRecorder(MediaStreamTrack):
    """Media track that directly records audio to a file."""

    kind = "audio"

    def __init__(self, track, path):
        super().__init__()
        self.track = track
        self.path = path
        self.sample_rate = 48000
        self.channels = 1
        self.sample_width = 2  # 16-bit audio
        self.frames = []
        self.frame_count = 0
        self.start_time = time.time()
        self.file = None
        self.wf = None
        
        # Open the file for direct writing
        try:
            self.wf = wave.open(self.path, 'wb')
            self.wf.setnchannels(self.channels)
            self.wf.setsampwidth(self.sample_width)
            self.wf.setframerate(self.sample_rate)
            print(f"Opened direct recording file: {self.path}")
        except Exception as e:
            print(f"Error opening direct recording file: {e}")
            self.wf = None
        
    async def recv(self):
        # Get the frame from the track we're wrapping
        try:
            frame = await self.track.recv()
            self.frame_count += 1
            
            # Process audio frames
            if isinstance(frame, AudioFrame) and len(frame.planes) > 0:
                # Extract audio data
                audio_data = bytes(frame.planes[0])
                self.frames.append(audio_data)
                
                # Print diagnostic info for first several frames
                if self.frame_count <= 10:
                    audio_array = np.frombuffer(audio_data, dtype=np.int16)
                    max_amplitude = np.max(np.abs(audio_array))
                    rms = np.sqrt(np.mean(np.square(audio_array)))
                    print(f"Received frame {self.frame_count}: {len(audio_data)} bytes, max amp={max_amplitude}, RMS={rms:.2f}")
                elif self.frame_count == 11:
                    print("Continuing to receive frames...")
                elif self.frame_count % 50 == 0:
                    print(f"Received {self.frame_count} frames")
                
                # Write directly to the file if available
                if self.wf:
                    try:
                        self.wf.writeframes(audio_data)
                    except Exception as e:
                        print(f"Error writing to direct recording: {e}")
            else:
                print(f"Received non-audio frame or empty planes: {type(frame)}")
                
            return frame
            
        except Exception as e:
            print(f"Error in DirectAudioRecorder.recv(): {e}")
            # Create a silent frame as fallback
            silent_frame = AudioFrame(
                format="s16",
                layout="mono",
                samples=1024,
            )
            silent_frame.pts = int((time.time() - self.start_time) * self.sample_rate)
            silent_frame.sample_rate = self.sample_rate
            silent_frame.time_base = f"1/{self.sample_rate}"
            
            # Fill with silence
            silence = np.zeros(1024, dtype=np.int16)
            silent_frame.planes[0].update(silence.tobytes())
            return silent_frame
        
    def stop(self):
        """Stop recording and close the file."""
        print(f"Stopping DirectAudioRecorder after {self.frame_count} frames")
        if self.wf:
            try:
                self.wf.close()
                print(f"Closed direct recording file")
                if os.path.exists(self.path):
                    size = os.path.getsize(self.path)
                    print(f"Direct recording file size: {size} bytes")
            except Exception as e:
                print(f"Error closing direct recording file: {e}")
        
        # Also save to a backup file using the collected frames
        if self.frames:
            try:
                backup_path = self.path + ".backup.wav"
                with wave.open(backup_path, 'wb') as wf:
                    wf.setnchannels(self.channels)
                    wf.setsampwidth(self.sample_width)
                    wf.setframerate(self.sample_rate)
                    wf.writeframes(b''.join(self.frames))
                print(f"Saved {len(self.frames)} frames to backup file: {backup_path}")
            except Exception as e:
                print(f"Error saving backup file: {e}")
        else:
            print("No frames collected for backup file")

async def run_server():
    # Initialize variables
    server_socket = None
    conn = None
    pc = None
    recorder = None
    direct_recorder = None
    tasks = set()
    track_received = False
    
    # Determine where to save the recording
    recording_path = DEFAULT_RECORDING_PATH
    
    try:
        # Try to create a test file to check write permissions
        try:
            with open("test_write.txt", "w") as f:
                f.write("test")
            os.remove("test_write.txt")
            print("Write permission test: OK")
        except Exception as e:
            print(f"WARNING: Write permission test failed: {e}")
            print("Will try to save in user's home directory instead")
            recording_path = os.path.join(os.path.expanduser("~"), "server_received.wav")
            print(f"New recording path: {recording_path}")
        
        server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server_socket.bind(('localhost', SIGNALING_PORT))
        server_socket.listen(1)
        print(f"Server listening on port {SIGNALING_PORT}")
        print(f"Will save recording to: {recording_path}")
        print(f"Will save direct recording to: {DIRECT_RECORD_PATH}")

        conn, addr = server_socket.accept()
        print(f"Connection from {addr}")

        # Create a relay for audio tracks to prevent any "track ended" issues
        relay = MediaRelay()
        
        # Create peer connection
        pc = RTCPeerConnection()
        
        # Create recorder with the determined path
        recorder = MediaRecorder(recording_path)
        recording_done = threading.Event()
        
        # Monitor connection state
        connection_established = asyncio.Event()
        
        @pc.on("connectionstatechange")
        async def on_connectionstatechange():
            print(f"Connection state: {pc.connectionState}")
            if pc.connectionState == "connected":
                connection_established.set()
                print("ICE connection established - should be receiving audio now")
            elif pc.connectionState in ["failed", "closed", "disconnected"]:
                print(f"Connection is in {pc.connectionState} state")
                if not recording_done.is_set():
                    recording_done.set()

        @pc.on("track")
        async def on_track(track):
            nonlocal track_received, direct_recorder
            track_received = True
            print(f"Receiving {track.kind} track of type {type(track).__name__}")
            
            if track.kind == "audio":
                # Use a relay to ensure the track stays alive
                relayed_track = relay.subscribe(track)
                
                # Create our direct recorder
                direct_recorder = DirectAudioRecorder(relayed_track, DIRECT_RECORD_PATH)
                
                # Also add track to aiortc recorder
                recorder.addTrack(relayed_track)
                
                # Start recorder
                try:
                    await recorder.start()
                    print(f"Started recording incoming audio to {recording_path}")
                except Exception as e:
                    print(f"Failed to start recorder: {e}")
                
                # Start a separate task to actively pull frames from the track
                async def pull_frames():
                    print("Started frame pulling task")
                    frame_count = 0
                    try:
                        while not recording_done.is_set():
                            try:
                                frame = await direct_recorder.recv()
                                frame_count += 1
                                if frame_count % 100 == 0:
                                    print(f"Pulled {frame_count} frames")
                            except Exception as e:
                                print(f"Error pulling frame: {e}")
                                await asyncio.sleep(0.1)
                    except asyncio.CancelledError:
                        print("Frame pulling task cancelled")
                    except Exception as e:
                        print(f"Frame pulling task error: {e}")
                    finally:
                        print(f"Frame pulling task ended after {frame_count} frames")
                
                pull_task = asyncio.create_task(pull_frames())
                tasks.add(pull_task)
            
            # Schedule recording stop after RECORD_SECONDS
            async def stop_recording_after_timeout():
                await asyncio.sleep(RECORD_SECONDS)
                if not recording_done.is_set():
                    print(f"Recording time limit reached ({RECORD_SECONDS}s)")
                    recording_done.set()
            
            timeout_task = asyncio.create_task(stop_recording_after_timeout())
            tasks.add(timeout_task)

        # Receive SDP offer
        offer_data = json.loads(conn.recv(65536).decode())
        offer = RTCSessionDescription(sdp=offer_data["sdp"], type=offer_data["type"])
        
        # Print incoming SDP for debugging
        print("Received SDP offer - checking audio configuration:")
        # Look for audio codec information in the SDP
        sdp_lines = offer.sdp.splitlines()
        for line in sdp_lines:
            if "opus" in line.lower() or "audio" in line.lower() or "m=audio" in line:
                print(f"SDP audio config: {line}")
        
        await pc.setRemoteDescription(offer)

        # Send SDP answer
        answer = await pc.createAnswer()
        await pc.setLocalDescription(answer)
        
        # Print our SDP answer for debugging
        print("Sending SDP answer with audio configuration:")
        for line in pc.localDescription.sdp.splitlines():
            if "opus" in line.lower() or "audio" in line.lower() or "m=audio" in line:
                print(f"SDP answer: {line}")
                
        response = json.dumps({
            "sdp": pc.localDescription.sdp,
            "type": pc.localDescription.type
        }).encode()
        conn.sendall(response)

        # Wait for recording to complete or timeout
        try:
            # Check every 100ms if recording has finished
            for i in range(int((RECORD_SECONDS + 3) * 10)):  # Wait max RECORD_SECONDS + 3 seconds
                if recording_done.is_set():
                    print("Recording completed")
                    break
                if i % 20 == 0:  # Every 2 seconds
                    print(f"Still waiting for recording to complete: {i/10:.1f}s elapsed")
                await asyncio.sleep(0.1)
        except Exception as e:
            print(f"Exception while waiting for recording: {e}")

    except Exception as e:
        print(f"Server error: {e}")
    finally:
        # Cleanup resources in reverse order of creation
        print("Stopping recording and cleaning up...")
        
        # Cancel any pending tasks
        for task in tasks:
            if not task.done():
                task.cancel()
                
        # Wait a moment for tasks to clean up
        await asyncio.sleep(0.5)
        
        # Stop direct recorder if available
        if direct_recorder:
            direct_recorder.stop()
        
        # Properly close recorder and PC with error handling
        if recorder:
            try:
                print("Stopping recorder...")
                await recorder.stop()
                print(f"Recorder stopped successfully")
            except Exception as e:
                print(f"Error stopping recorder: {e}")
        
        if pc:
            try:
                await pc.close()
            except Exception as e:
                print(f"Error closing WebRTC connection: {e}")
        
        # Close socket connections
        if conn:
            conn.close()
        
        if server_socket:
            server_socket.close()
        
        # Verify files exist
        for path in [recording_path, DIRECT_RECORD_PATH, DIRECT_RECORD_PATH + ".backup.wav"]:
            if path and os.path.exists(path):
                file_size = os.path.getsize(path)
                print(f"Saved recording to {path} ({file_size} bytes)")
                if file_size == 0:
                    print(f"WARNING: File exists but is empty: {path}")
            elif path:
                print(f"WARNING: Recording file not found at {path}")
        
        if track_received:
            print(f"Track was received - check the logs for details")
        else:
            print("No audio track was received from client")

if __name__ == "__main__":
    try:
        asyncio.run(run_server())
    except KeyboardInterrupt:
        print("Server terminated by user")
    except Exception as e:
        print(f"Error: {e}")
    finally:
        print("Exiting server")
