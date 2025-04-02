import asyncio
import os
import time
import uuid
import wave
from typing import Dict, List

import av
import uvicorn
from aiortc import MediaStreamTrack, RTCPeerConnection, RTCSessionDescription
from aiortc.contrib.media import MediaRecorder
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

app = FastAPI()

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
client_cleanup_lock: Dict[str, bool] = {}  # Track if cleanup is in progress


# Audio processing class
class AudioTrackProcessor(MediaStreamTrack):
    kind = "audio"

    def __init__(self, track, client_id):
        super().__init__()
        self.track = track
        self.client_id = client_id
        self.frame_count = 0
        self.sample_rate = 48000  # Default, will be updated from frame

    async def recv(self):
        frame = await self.track.recv()
        self.frame_count += 1

        # Update sample rate from frame if available
        if hasattr(frame, "rate") and frame.rate is not None:
            self.sample_rate = frame.rate

        # Convert frame to bytes and store
        if self.client_id in audio_frames:
            try:
                # Try to get audio samples directly
                pcm_bytes = None

                # First try direct bytes conversion
                if hasattr(frame, "to_ndarray"):
                    try:
                        # Get raw audio data
                        array = frame.to_ndarray()
                        pcm_bytes = array.tobytes()
                    except Exception as e:
                        print(f"Error in to_ndarray: {e}")

                # If that fails, try getting the plane data directly
                if (
                    pcm_bytes is None
                    and hasattr(frame, "planes")
                    and len(frame.planes) > 0
                ):
                    try:
                        pcm_bytes = bytes(frame.planes[0])
                    except Exception as e:
                        print(f"Error extracting plane data: {e}")

                # If we have audio data, store it
                if pcm_bytes:
                    audio_frames[self.client_id].append(pcm_bytes)

                    # Log occasionally to avoid flooding
                    if self.frame_count % 100 == 0:
                        total_kb = (
                            sum(len(b) for b in audio_frames[self.client_id]) / 1024
                        )
                        audio_sec = (
                            len(audio_frames[self.client_id])
                            * len(pcm_bytes)
                            / (2 * self.sample_rate)
                        )
                        print(
                            f"Processed {self.frame_count} frames for client {self.client_id} - Total: {total_kb:.1f} KB ({audio_sec:.1f} sec)"
                        )
                else:
                    if self.frame_count % 100 == 0:
                        print(
                            f"Warning: Could not extract audio data from frame {self.frame_count}"
                        )
            except Exception as e:
                print(f"Error processing audio frame: {e}")

        return frame


class OfferModel(BaseModel):
    sdp: str
    type: str


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

    # Prepare audio file path
    os.makedirs("recordings", exist_ok=True)
    timestamp = time.strftime("%Y%m%d-%H%M%S")
    audio_file = f"recordings/audio_{timestamp}_{client_id[-8:]}.wav"

    # Initialize frame storage
    audio_frames[client_id] = []

    # Create recorder
    recorder = MediaRecorder(audio_file)
    recorders[client_id] = recorder

    @pc.on("track")
    def on_track(track):
        print(f"Track received: {track.kind}")
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
                if client_id in pcs:  # Only cleanup if client still exists
                    await cleanup(client_id)
            except Exception as e:
                print(f"Error in track.ended handler: {e}")

    @pc.on("connectionstatechange")
    async def on_connectionstatechange():
        print(f"Connection state for {client_id}: {pc.connectionState}")
        if pc.connectionState == "failed" or pc.connectionState == "closed":
            try:
                if client_id in pcs:  # Only cleanup if client still exists
                    await cleanup(client_id)
            except Exception as e:
                print(f"Error in connectionstatechange: {e}")

    # Set the remote description
    await pc.setRemoteDescription(offer)
    await recorder.start()
    print(f"Recorder started for client {client_id}, writing to {audio_file}")

    # Create answer
    answer = await pc.createAnswer()
    await pc.setLocalDescription(answer)

    return {"sdp": pc.localDescription.sdp, "type": pc.localDescription.type}


async def cleanup(client_id):
    # Prevent duplicate cleanups
    if client_id not in pcs or client_cleanup_lock.get(client_id, False):
        return

    # Mark this client as being cleaned up
    client_cleanup_lock[client_id] = True

    try:
        pc = pcs[client_id]

        # Stop recorder if exists
        if client_id in recorders:
            recorder = recorders[client_id]
            print(f"Stopping recorder for client {client_id}")
            await recorder.stop()
            del recorders[client_id]

            # Save raw audio as fallback method
            if client_id in audio_frames and audio_frames[client_id]:
                try:
                    timestamp = time.strftime("%Y%m%d-%H%M%S")
                    fallback_path = (
                        f"recordings/fallback_{timestamp}_{client_id[-8:]}.wav"
                    )
                    frames = audio_frames[client_id]
                    total_size = sum(len(frame) for frame in frames)
                    print(
                        f"Saving {len(frames)} frames ({total_size/1024:.1f} KB) to fallback file {fallback_path}"
                    )

                    # Write raw audio to wav file
                    with wave.open(fallback_path, "wb") as wf:
                        wf.setnchannels(1)  # Mono
                        wf.setsampwidth(2)  # 2 bytes (16 bits)
                        wf.setframerate(48000)  # 48 kHz
                        wf.writeframes(b"".join(frames))

                    file_size = os.path.getsize(fallback_path)
                    print(
                        f"Fallback audio saved to {fallback_path} ({file_size/1024:.1f} KB)"
                    )

                    # List files in recordings directory
                    files = os.listdir("recordings")
                    print(f"Recording directory contains {len(files)} files:")
                    for file in files:
                        file_path = os.path.join("recordings", file)
                        file_size = os.path.getsize(file_path)
                        print(f"- {file}: {file_size/1024:.1f} KB")
                except Exception as e:
                    print(f"Error saving fallback audio: {e}")
            else:
                print(f"No frames to save for client {client_id}")

            # Clean up audio frames
            if client_id in audio_frames:
                del audio_frames[client_id]

        # Close peer connection
        await pc.close()

        # Delete the peer connection from dictionaries
        if client_id in pcs:
            del pcs[client_id]

        if client_id in client_cleanup_lock:
            del client_cleanup_lock[client_id]

    except Exception as e:
        print(f"Error during cleanup for {client_id}: {e}")


@app.on_event("shutdown")
async def on_shutdown():
    # Close all peer connections and stop all recorders
    tasks = [cleanup(client_id) for client_id in list(pcs.keys())]
    await asyncio.gather(*tasks)
    print("All recorders stopped and connections closed")

    # Check if any recordings were created
    if os.path.exists("recordings"):
        files = os.listdir("recordings")
        print(f"Recording directory contains {len(files)} files: {files}")


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
                
                startButton.addEventListener('click', async () => {
                    startButton.disabled = true;
                    
                    pc = new RTCPeerConnection();
                    
                    try {
                        const stream = await navigator.mediaDevices.getUserMedia({ audio: true, video: false });
                        stream.getTracks().forEach(track => pc.addTrack(track, stream));
                        
                        pc.oniceconnectionstatechange = () => {
                            console.log('ICE connection state:', pc.iceConnectionState);
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
                        await pc.setRemoteDescription(answer);
                        
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
