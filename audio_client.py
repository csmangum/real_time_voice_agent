#!/usr/bin/env python3
import asyncio
import json
import uuid
import wave
import os
import argparse
import logging
from datetime import datetime

import pyaudio
import av
import numpy as np
import requests
from aiortc import RTCPeerConnection, RTCSessionDescription, MediaStreamTrack
from aiortc.contrib.media import MediaRecorder

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("audio_client")

# Create output directory for local recordings
os.makedirs("local_recordings", exist_ok=True)

# Audio parameters
SAMPLE_RATE = 48000
CHANNELS = 1
FORMAT = pyaudio.paInt16
CHUNK = 960  # 20ms at 48kHz

class MicrophoneStreamTrack(MediaStreamTrack):
    """MediaStreamTrack that captures audio from microphone."""
    
    kind = "audio"
    
    def __init__(self):
        super().__init__()
        self.p = pyaudio.PyAudio()
        self.stream = self.p.open(
            format=FORMAT,
            channels=CHANNELS,
            rate=SAMPLE_RATE,
            input=True,
            frames_per_buffer=CHUNK
        )
        self.local_frames = []  # Store frames for local recording
        self.timestamp = 0  # Add timestamp counter
        logger.info(f"Microphone initialized: {SAMPLE_RATE}Hz, {CHANNELS} channel(s)")
    
    async def recv(self):
        """Get frame from microphone."""
        data = self.stream.read(CHUNK, exception_on_overflow=False)
        self.local_frames.append(data)  # Save for local recording
        
        # Convert audio data to frame
        frame = av.AudioFrame.from_ndarray(
            np.frombuffer(data, np.int16).reshape(1, -1),
            format="s16",
            layout="mono" if CHANNELS == 1 else "stereo"
        )
        frame.sample_rate = SAMPLE_RATE
        frame.pts = self.timestamp  # Set presentation timestamp
        self.timestamp += CHUNK  # Increment by samples processed
        
        return frame
    
    def stop(self):
        """Stop the microphone stream."""
        if self.stream:
            self.stream.stop_stream()
            self.stream.close()
        if self.p:
            self.p.terminate()
        logger.info("Microphone stopped")
    
    def save_local_recording(self, filename):
        """Save captured audio to a local WAV file."""
        if not self.local_frames:
            logger.warning("No audio frames to save")
            return
        
        with wave.open(filename, 'wb') as wf:
            wf.setnchannels(CHANNELS)
            wf.setsampwidth(self.p.get_sample_size(FORMAT))
            wf.setframerate(SAMPLE_RATE)
            wf.writeframes(b''.join(self.local_frames))
        
        logger.info(f"Local recording saved to {filename}")

async def run_client(server_url, recording_time):
    # Generate a client ID
    client_id = str(uuid.uuid4())
    local_filename = f"local_recordings/local_{client_id}.wav"
    
    logger.info(f"Starting audio client with ID: {client_id}")
    logger.info(f"Will record for {recording_time} seconds")
    logger.info(f"Local recording will be saved to: {local_filename}")
    
    # Create peer connection
    pc = RTCPeerConnection()
    
    # Create microphone track
    mic_track = MicrophoneStreamTrack()
    
    # Add track to peer connection
    pc.addTrack(mic_track)
    
    # For debugging
    @pc.on("connectionstatechange")
    async def on_connectionstatechange():
        logger.info(f"Connection state: {pc.connectionState}")
        if pc.connectionState == "failed":
            await cleanup(pc, mic_track, client_id, server_url)
    
    # Create offer
    offer = await pc.createOffer()
    await pc.setLocalDescription(offer)
    
    # Send offer to server
    logger.info(f"Sending offer to server: {server_url}/offer")
    response = requests.post(
        f"{server_url}/offer",
        json={"sdp": pc.localDescription.sdp, "type": pc.localDescription.type}
    )
    
    if response.status_code != 200:
        logger.error(f"Server returned error: {response.status_code}")
        await cleanup(pc, mic_track, client_id, server_url)
        return
    
    # Process the server's answer
    answer_data = response.json()
    server_client_id = answer_data.get("client_id", client_id)  # Get client ID from server if available
    logger.info(f"Server assigned client ID: {server_client_id}")
    
    answer = RTCSessionDescription(sdp=answer_data["sdp"], type=answer_data["type"])
    await pc.setRemoteDescription(answer)
    
    logger.info("Connection established with server")
    
    try:
        # Record for the specified duration
        await asyncio.sleep(recording_time)
    except KeyboardInterrupt:
        logger.info("Recording stopped by user")
    finally:
        # Save local recording and clean up
        mic_track.save_local_recording(local_filename)
        await cleanup(pc, mic_track, server_client_id, server_url)

async def cleanup(pc, mic_track, client_id, server_url):
    """Clean up resources."""
    logger.info("Cleaning up...")
    
    # Stop the microphone
    mic_track.stop()
    
    # Give server a moment to process any final audio frames
    logger.info("Waiting for server to process final audio frames...")
    await asyncio.sleep(2)
    
    # Close the peer connection
    await pc.close()
    
    # Wait a bit longer for server to close the recorder
    await asyncio.sleep(2)
    
    # Notify the server
    try:
        requests.post(
            f"{server_url}/disconnect",
            json={"client_id": client_id}
        )
        logger.info("Sent disconnect signal to server")
    except Exception as e:
        logger.error(f"Failed to send disconnect signal: {str(e)}")
    
    logger.info("Cleanup complete")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Audio streaming client")
    parser.add_argument("--server", type=str, default="http://localhost:8000",
                        help="Server URL (default: http://localhost:8000)")
    parser.add_argument("--time", type=int, default=10,
                        help="Recording time in seconds (default: 10)")
    args = parser.parse_args()
    
    # Start the client
    asyncio.run(run_client(args.server, args.time)) 