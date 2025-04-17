import asyncio
import socket
import json
import pyaudio
import wave
import threading
import time
from aiortc import RTCPeerConnection, RTCSessionDescription
from aiortc.contrib.media import MediaStreamTrack
from av import AudioFrame
import numpy as np
import os

SIGNALING_PORT = 9999
CHUNK = 1024
FORMAT = pyaudio.paInt16
CHANNELS = 1
RATE = 48000  # Standard rate for WebRTC
RECORD_SECONDS = 10  # Set recording time to 10 seconds

class PyAudioStreamTrack(MediaStreamTrack):
    kind = "audio"
    
    def __init__(self):
        super().__init__()
        self.p = pyaudio.PyAudio()
        # List available input devices
        print("Available audio input devices:")
        for i in range(self.p.get_device_count()):
            dev_info = self.p.get_device_info_by_index(i)
            print(f"Device {i}: {dev_info['name']} (inputs: {dev_info['maxInputChannels']})")
        
        # Open stream
        self.stream = self.p.open(
            format=FORMAT,
            channels=CHANNELS,
            rate=RATE,
            input=True,
            frames_per_buffer=CHUNK
        )
        print(f"Opened audio input stream: format={FORMAT}, channels={CHANNELS}, rate={RATE}")
        
        self.sample_count = 0
        self.recording = False
        self.frames = []
        self.frame_count = 0
        self.recording_finished = threading.Event()
        self._start_recording()
        
    def _start_recording(self):
        self.recording = True
        self.record_thread = threading.Thread(target=self._record_audio, daemon=True)
        self.record_thread.start()
        
    def _record_audio(self):
        start_time = time.time()
        while self.recording and (time.time() - start_time) < RECORD_SECONDS:
            try:
                data = self.stream.read(CHUNK, exception_on_overflow=False)
                
                # Quick audio level check for first few chunks
                if len(self.frames) < 5:
                    audio_array = np.frombuffer(data, dtype=np.int16)
                    max_amplitude = np.max(np.abs(audio_array))
                    rms = np.sqrt(np.mean(np.square(audio_array)))
                    print(f"Audio chunk {len(self.frames)}: max={max_amplitude}, RMS={rms:.2f}")
                
                self.frames.append(data)
            except Exception as e:
                print(f"Error reading audio: {e}")
                break
        
        # Signal that recording is complete without calling stop()
        print(f"Finished recording ({RECORD_SECONDS} seconds)")
        self.recording_finished.set()
            
    async def recv(self):
        # Make sure we always return a valid frame, even if no data is available yet
        if not self.frames and not self.recording_finished.is_set():
            print("No frames yet, waiting...")
            await asyncio.sleep(0.1)
            # Return silence frame
            silence = np.zeros(CHUNK, dtype=np.int16)
            frame = AudioFrame(format="s16", layout="mono", samples=CHUNK)
            frame.pts = self.sample_count
            frame.sample_rate = RATE
            frame.time_base = "1/48000"
            self.sample_count += CHUNK
            frame.planes[0].update(silence.tobytes())
            return frame
            
        if self.frames:
            self.frame_count += 1
            frame_data = self.frames.pop(0)
            
            # Ensure frame data is the right size and format
            if len(frame_data) != CHUNK * 2:  # 2 bytes per sample for int16
                print(f"Warning: Unexpected frame size: {len(frame_data)} bytes")
                # Pad or truncate to expected size
                if len(frame_data) < CHUNK * 2:
                    frame_data = frame_data + bytes(CHUNK * 2 - len(frame_data))
                else:
                    frame_data = frame_data[:CHUNK * 2]
            
            # Create the frame
            frame = AudioFrame(
                format="s16",
                layout="mono",
                samples=CHUNK,
            )
            frame.pts = self.sample_count
            frame.sample_rate = RATE
            frame.time_base = "1/48000"
            self.sample_count += CHUNK
            
            # Convert bytes to numpy array
            frame_array = np.frombuffer(frame_data, dtype=np.int16)
            
            # Increase amplitude if needed - multiply by 10 to ensure it's audible
            # Only do this if the original max amplitude is very low
            max_amplitude = np.max(np.abs(frame_array))
            if max_amplitude < 100:  # If very quiet
                print(f"Amplifying quiet audio: max amplitude before={max_amplitude}")
                frame_array = np.clip(frame_array * 100, -32768, 32767).astype(np.int16)
                max_amplitude = np.max(np.abs(frame_array))
                print(f"After amplification: max amplitude={max_amplitude}")
            
            # Populate the plane with audio data
            frame.planes[0].update(frame_array.tobytes())
            
            # Print diagnostic info
            if self.frame_count <= 5:
                print(f"Sending frame {self.frame_count}: {len(frame_data)} bytes, max amplitude: {max_amplitude}")
            elif self.frame_count == 6:
                print("Continuing to send frames...")
            elif self.frame_count % 50 == 0:
                print(f"Sent {self.frame_count} frames")
                
            return frame
        
        # If we're done recording and no more frames, return None to end the track
        if self.recording_finished.is_set():
            print("No more frames to send, ending audio track")
            return None
            
        # Fallback - should never reach here
        print("Warning: Unexpected state in recv()")
        return None
        
    def stop(self):
        print("Stopping audio track...")
        self.recording = False
        
        # Wait for the recording thread to finish if it's still running
        # Only join from external threads, not from the recording thread itself
        if (hasattr(self, 'record_thread') and 
            self.record_thread.is_alive() and 
            threading.current_thread() != self.record_thread):
            self.record_thread.join(timeout=2)
            
        if self.stream:
            self.stream.stop_stream()
            self.stream.close()
        if self.p:
            self.p.terminate()
            
        # Save the recorded audio to a file
        if self.frames:
            try:
                output_path = os.path.abspath("client_sent.wav")
                wf = wave.open(output_path, 'wb')
                wf.setnchannels(CHANNELS)
                wf.setsampwidth(self.p.get_sample_size(FORMAT))
                wf.setframerate(RATE)
                wf.writeframes(b''.join(self.frames))
                wf.close()
                print(f"Saved recording to {output_path}")
            except Exception as e:
                print(f"Error saving recording: {e}")
        else:
            print("No frames left to save")

async def run_client():
    # Track all tasks to ensure proper cleanup
    tasks = set()
    client_socket = None
    pc = None
    audio_track = None
    
    try:
        # Configure WebRTC with proper constraints
        pc = RTCPeerConnection()
        print("Starting client...")

        # Create PyAudio track
        audio_track = PyAudioStreamTrack()
        sender = pc.addTrack(audio_track)
        
        # Create and send offer with audio enabled
        offer = await pc.createOffer()
        await pc.setLocalDescription(offer)
        
        # Check SDP for audio settings
        print("SDP Offer created with the following audio settings:")
        for line in pc.localDescription.sdp.splitlines():
            if "opus" in line.lower() or "audio" in line.lower() or "m=audio" in line:
                print(f"SDP: {line}")

        client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        client_socket.connect(('localhost', SIGNALING_PORT))
        client_socket.sendall(json.dumps({
            "sdp": pc.localDescription.sdp,
            "type": pc.localDescription.type
        }).encode())
        print("Sent SDP offer to server")

        # Receive and apply answer
        answer_data = json.loads(client_socket.recv(65536).decode())
        answer = RTCSessionDescription(sdp=answer_data["sdp"], type=answer_data["type"])
        await pc.setRemoteDescription(answer)
        print("Received SDP answer from server")
        
        # Create a task for the connection establishment
        connection_established = asyncio.Event()
        
        @pc.on("connectionstatechange")
        async def on_connectionstatechange():
            print(f"Connection state: {pc.connectionState}")
            if pc.connectionState == "connected":
                connection_established.set()
                print("ICE connection established - audio should now be flowing")
            elif pc.connectionState == "failed":
                print("ICE connection failed - check network and firewall settings")
        
        # Wait for either connection establishment or timeout
        try:
            # Wait for connection (with timeout) before proceeding
            connection_wait_task = asyncio.create_task(
                asyncio.wait_for(connection_established.wait(), timeout=5)
            )
            tasks.add(connection_wait_task)
            await connection_wait_task
            print("WebRTC connection established")
        except asyncio.TimeoutError:
            print("Connection establishment timed out, continuing anyway")
        except Exception as e:
            print(f"Connection error: {e}")

        # Keep streaming audio for the recording duration
        try:
            for _ in range(int(RECORD_SECONDS * 2)):  # Check twice per second
                if audio_track.recording_finished.is_set():
                    print("Recording completed naturally")
                    # Keep the connection open a bit longer to ensure all data is sent
                    await asyncio.sleep(2)
                    break
                await asyncio.sleep(0.5)
        except Exception as e:
            print(f"Exception while waiting for recording: {e}")
        
    except Exception as e:
        print(f"Client error: {e}")
    finally:
        # Cleanup resources in reverse order of creation
        print("Cleaning up resources...")
        
        # Cancel any pending tasks
        for task in tasks:
            if not task.done():
                task.cancel()
                
        # Stop audio track
        if audio_track:
            audio_track.stop()
            
        # Close WebRTC connection 
        if pc:
            # Create a task for graceful closure
            close_task = asyncio.create_task(pc.close())
            try:
                await asyncio.wait_for(close_task, timeout=2)
            except asyncio.TimeoutError:
                print("WebRTC connection closure timed out")
            except Exception as e:
                print(f"Error during WebRTC connection closure: {e}")
                
        # Close socket
        if client_socket:
            client_socket.close()
            
        print("Client finished.")

if __name__ == "__main__":
    try:
        asyncio.run(run_client())
    except KeyboardInterrupt:
        print("Client terminated by user")
    except Exception as e:
        print(f"Error: {e}")
    finally:
        print("Exiting client")
