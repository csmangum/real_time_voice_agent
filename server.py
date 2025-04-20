import asyncio
import logging
import os
import time
import traceback
import uuid
import wave
from datetime import datetime
from typing import Dict, List

from aiortc import RTCPeerConnection, RTCSessionDescription
from aiortc.contrib.media import MediaPlayer, MediaRecorder, MediaRelay
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

# Set up logging
# Ensure logs directory exists
os.makedirs("logs", exist_ok=True)

# Create a unique log filename with timestamp
log_filename = f"logs/server_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

# Set up logging to both console and file
logger = logging.getLogger("WebRTC-Server")
logger.setLevel(logging.DEBUG)  # Set to DEBUG for more detailed logs

# Create console handler
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.DEBUG)

# Create file handler
file_handler = logging.FileHandler(log_filename)
file_handler.setLevel(logging.DEBUG)

# Create formatter and add it to the handlers
formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
console_handler.setFormatter(formatter)
file_handler.setFormatter(formatter)

# Add handlers to logger
logger.addHandler(console_handler)
logger.addHandler(file_handler)

logger.info(f"Logging to file: {log_filename}")

app = FastAPI()

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")

# Create a media relay for sharing a single media source
relay = MediaRelay()

# Store active peer connections
peer_connections: Dict[str, RTCPeerConnection] = {}

# Store audio recorders
audio_recorders: Dict[str, MediaRecorder] = {}

# Ensure recordings directory exists
os.makedirs("server_recordings", exist_ok=True)


@app.post("/offer")
async def offer(request: Request):
    try:
        data = await request.json()
        offer = RTCSessionDescription(sdp=data["sdp"], type=data["type"])
        pc_id = str(uuid.uuid4())
        logger.info(f"Received offer from client, created PC with ID: {pc_id}")

        # Create a new WebRTC connection
        pc = RTCPeerConnection()
        peer_connections[pc_id] = pc

        # Create recording filename
        timestamp = int(time.time())
        recording_filename = f"server_recordings/client_audio_{pc_id}_{timestamp}.wav"
        recorder = MediaRecorder(recording_filename)
        audio_recorders[pc_id] = recorder

        # Track ICE candidates
        @pc.on("icecandidate")
        def on_icecandidate(candidate):
            logger.info(f"Generated ICE candidate: {candidate}")

        # Handle tracks received from client
        @pc.on("track")
        async def on_track(track):
            logger.info(f"Received {track.kind} track from client")

            if track.kind == "audio":
                logger.info(f"Recording client audio to {recording_filename}")
                recorder.addTrack(track)
                await recorder.start()

                @track.on("ended")
                async def on_ended():
                    logger.info(f"Client audio track ended, stopping recorder")
                    await recorder.stop()

        # Handle cleanup when client disconnects
        @pc.on("connectionstatechange")
        async def on_connectionstatechange():
            logger.info(f"Connection state changed to: {pc.connectionState}")
            if (
                pc.connectionState == "failed"
                or pc.connectionState == "closed"
                or pc.connectionState == "disconnected"
            ):
                logger.info(
                    f"Connection {pc_id} is {pc.connectionState}, cleaning up resources"
                )

                # Stop the recorder if it's still running
                if pc_id in audio_recorders:
                    try:
                        recorder = audio_recorders[pc_id]
                        logger.info(
                            f"Stopping recording client audio to {recording_filename}"
                        )
                        await recorder.stop()
                        logger.info(
                            f"Successfully stopped recording to {recording_filename}"
                        )
                        del audio_recorders[pc_id]
                    except Exception as e:
                        logger.error(f"Error stopping recorder: {e}")
                        logger.error(traceback.format_exc())

                # Remove peer connection from active connections
                if pc_id in peer_connections:
                    try:
                        # Close the peer connection if not already closed
                        if pc.connectionState != "closed":
                            await pc.close()
                        del peer_connections[pc_id]
                        logger.info(f"Successfully removed connection {pc_id}")
                    except Exception as e:
                        logger.error(f"Error closing peer connection: {e}")
                        logger.error(traceback.format_exc())
                        # Still try to remove from dictionary even if close fails
                        if pc_id in peer_connections:
                            del peer_connections[pc_id]

        # Set up audio stream from sample.wav
        try:
            # Check if the file exists and is a valid audio file
            audio_file_path = "static/sample.wav"
            logger.debug(f"Attempting to open audio file: {audio_file_path}")

            with wave.open(audio_file_path, "rb") as wave_file:
                info = {
                    "channels": wave_file.getnchannels(),
                    "sample_width": wave_file.getsampwidth(),
                    "framerate": wave_file.getframerate(),
                    "frames": wave_file.getnframes(),
                }
                logger.debug(f"Audio file info: {info}")

            # Create the media player for the audio file with improved options
            player = MediaPlayer(
                audio_file_path,
                loop=True,  # Loop the audio for testing
                options={
                    "channels": "1",  # Force mono
                    "sample_fmt": "s16",  # Force 16-bit signed PCM
                    "buffer_size": "4096",  # Larger buffer for stability
                    "audio_jitter_buffer": "1000",  # Add 1000ms jitter buffer
                    "clock_rate": "48000",  # Force 48kHz sample rate for WebRTC
                    "packetization": "10",  # 10ms packetization time
                },
            )

            if player.audio:
                logger.info("Audio track created successfully")
                audio_track = relay.subscribe(player.audio)
                pc.addTrack(audio_track)
                logger.info("Added audio track to peer connection")
            else:
                logger.warning("No audio track found in sample.wav")
        except Exception as e:
            logger.error(f"Error setting up audio track: {e}")
            logger.error(traceback.format_exc())
            # Continue without audio if there's an error

        # Set the remote description
        try:
            logger.info("Setting remote description with offer from client")
            logger.debug(f"Offer SDP: {offer.sdp}")
            await pc.setRemoteDescription(offer)
            logger.info("Remote description set")
        except Exception as e:
            logger.error(f"Error setting remote description: {e}")
            logger.error(traceback.format_exc())
            raise HTTPException(status_code=400, detail=str(e))

        # Create answer
        try:
            logger.info("Creating answer")
            answer = await pc.createAnswer()
            await pc.setLocalDescription(answer)
            logger.info("Local description set")
            logger.debug(f"Answer SDP: {pc.localDescription.sdp}")
        except Exception as e:
            logger.error(f"Error creating answer: {e}")
            logger.error(traceback.format_exc())
            raise HTTPException(status_code=500, detail=str(e))

        return {"sdp": pc.localDescription.sdp, "type": pc.localDescription.type}
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn

    logger.info("Starting WebRTC server on port 8000...")
    uvicorn.run(app, host="0.0.0.0", port=8000)
