"""
Real-Time Audio Streaming Server
================================

A FastAPI and aiortc-based server for receiving and recording real-time audio streams.

Client Requirements
------------------
1. WebRTC Support: Python client must use aiortc library for WebRTC functionality
2. Audio Encoding: Client should support common audio codecs (Opus preferred)
3. Audio Source: Client needs access to an audio source (microphone or audio file)
4. Signaling: Client must implement the signaling protocol to establish WebRTC connection:
   - Send SDP offer to '/offer' endpoint as POST request
   - Receive and process SDP answer from server response
   - Optional: Send disconnect request to '/disconnect' with client_id when done

Audio Stream Processing
----------------------
- All incoming audio is automatically saved to WAV files in the 'recordings' directory
- Each client connection gets a unique UUID and corresponding recording file
- Audio is processed through AudioProcessor which can be extended for custom processing
- The server handles connection lifecycle and properly cleans up resources

Storage and Persistence
----------------------
- All audio streams are automatically saved to WAV files
- Recordings are stored in the 'recordings' directory with filenames based on client UUIDs
- In Docker deployment, recordings are persisted via volume mapping to the host system
- Logs tracking all connection events are stored in the 'logs' directory

Required Python Client Dependencies
----------------------------------
- aiortc: For WebRTC functionality
- requests: For HTTP communication with server
- PyAudio: If streaming from microphone
- av: For audio encoding/decoding
"""

import asyncio
import os
import uuid
import logging
import sys
from typing import Dict, List
from datetime import datetime

import av
import numpy as np
from aiortc import MediaStreamTrack, RTCPeerConnection, RTCSessionDescription
from aiortc.contrib.media import MediaRecorder
from fastapi import FastAPI, WebSocket, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# Configure logging
log_directory = "logs"
os.makedirs(log_directory, exist_ok=True)
log_filename = f"{log_directory}/audio_server_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

# Set up logging format and handlers
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_filename),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("audio_server")

# Create the recordings directory if it doesn't exist
os.makedirs("recordings", exist_ok=True)
logger.info(f"Server starting. Recordings will be saved to: {os.path.abspath('recordings')}")
logger.info(f"Logs will be saved to: {os.path.abspath(log_filename)}")

# Create FastAPI app
app = FastAPI(title="Real-Time Audio Server")

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Add logging middleware
@app.middleware("http")
async def log_requests(request: Request, call_next):
    logger.info(f"Request received: {request.method} {request.url}")
    try:
        response = await call_next(request)
        logger.info(f"Response status: {response.status_code}")
        return response
    except Exception as e:
        logger.error(f"Request error: {str(e)}", exc_info=True)
        raise

# Store active peer connections and recorders
pcs: Dict[str, RTCPeerConnection] = {}
recorders: Dict[str, MediaRecorder] = {}

# Models for request/response
class RTCSessionDescriptionModel(BaseModel):
    sdp: str
    type: str

class RTCIceCandidateModel(BaseModel):
    candidate: str
    sdpMid: str
    sdpMLineIndex: int

class ClientResponse(BaseModel):
    client_id: str

# Custom audio track processor
class AudioProcessor(MediaStreamTrack):
    kind = "audio"
    
    def __init__(self, track, client_id):
        super().__init__()
        self.track = track
        self.client_id = client_id
        self.sample_rate = None
        self.channels = None
        self.frame_count = 0
        self.error_count = 0
        logger.info(f"Created AudioProcessor for client {client_id}")
        
    async def recv(self):
        try:
            frame = await self.track.recv()
            self.frame_count += 1
            
            # Detect audio format on first frame
            if self.frame_count == 1:
                self.sample_rate = frame.sample_rate
                # Layout may not have nb_channels attribute in some av versions
                if hasattr(frame.layout, 'nb_channels'):
                    self.channels = frame.layout.nb_channels
                else:
                    # Use the name attribute to determine channels
                    layout_name = frame.layout.name
                    self.channels = 1 if layout_name == 'mono' else 2 if layout_name == 'stereo' else 1
                logger.info(f"Audio format detected for client {self.client_id}: {self.sample_rate}Hz, {self.channels} channels")
            
            # Log occasional progress
            if self.frame_count % 100 == 0:
                logger.debug(f"Client {self.client_id} processed {self.frame_count} frames")
                
            return frame
        except Exception as e:
            self.error_count += 1
            logger.error(f"Error processing frame for client {self.client_id}: {str(e)}")
            if self.error_count > 5:
                logger.warning(f"Too many errors for client {self.client_id}, may need cleanup")
            raise

@app.get("/")
async def index():
    logger.info("Health check endpoint called")
    return {"status": "running", "message": "Real-time audio server is running"}

@app.post("/offer", response_model=RTCSessionDescriptionModel)
async def process_offer(session_desc: RTCSessionDescriptionModel):
    # Create unique client ID
    client_id = str(uuid.uuid4())
    logger.info(f"New connection request with client ID: {client_id}")
    
    # Create a new RTCPeerConnection
    pc = RTCPeerConnection()
    pcs[client_id] = pc
    
    # Log ICE connection state changes
    @pc.on("connectionstatechange")
    async def on_connectionstatechange():
        logger.info(f"Client {client_id} connection state changed to: {pc.connectionState}")
        if pc.connectionState == "failed":
            logger.warning(f"Connection failed for client {client_id}")
            await cleanup(client_id)
    
    # Log ICE gathering state changes
    @pc.on("icegatheringstatechange")
    async def on_icegatheringstatechange():
        logger.info(f"Client {client_id} ICE gathering state changed to: {pc.iceGatheringState}")
    
    # Log signaling state changes
    @pc.on("signalingstatechange")
    async def on_signalingstatechange():
        logger.info(f"Client {client_id} signaling state changed to: {pc.signalingState}")
    
    # Handle audio track
    @pc.on("track")
    async def on_track(track):
        if track.kind == "audio":
            logger.info(f"Received audio track from client {client_id}")
            
            # Process audio through our custom processor
            processed_track = AudioProcessor(track, client_id)
            
            # Set up recording
            recorder_path = f"recordings/{client_id}.wav"
            logger.info(f"Starting recorder for client {client_id} at {recorder_path}")
            recorder = MediaRecorder(recorder_path)
            recorders[client_id] = recorder
            recorder.addTrack(processed_track)
            
            try:
                await recorder.start()
                logger.info(f"Recorder started for client {client_id}")
            except Exception as e:
                logger.error(f"Failed to start recorder for client {client_id}: {str(e)}", exc_info=True)
            
            # Keep the connection alive
            @track.on("ended")
            async def on_ended():
                logger.info(f"Track ended for client {client_id}")
                await cleanup(client_id)
    
    try:
        # Set remote description from the client's offer
        logger.info(f"Setting remote description for client {client_id}")
        offer = RTCSessionDescription(sdp=session_desc.sdp, type=session_desc.type)
        await pc.setRemoteDescription(offer)
        
        # Create answer
        logger.info(f"Creating answer for client {client_id}")
        answer = await pc.createAnswer()
        await pc.setLocalDescription(answer)
        
        logger.info(f"Connection established with client {client_id}")
        
        # Return the answer to the client
        return {
            "sdp": pc.localDescription.sdp, 
            "type": pc.localDescription.type,
            "client_id": client_id  # Include client ID in response
        }
    except Exception as e:
        logger.error(f"Error establishing connection with client {client_id}: {str(e)}", exc_info=True)
        await cleanup(client_id)
        raise

@app.post("/disconnect")
async def disconnect(client: ClientResponse):
    client_id = client.client_id
    logger.info(f"Disconnect request for client {client_id}")
    
    if client_id in pcs:
        await cleanup(client_id)
        logger.info(f"Client {client_id} successfully disconnected")
        return {"message": f"Client {client_id} disconnected"}
    
    logger.warning(f"Disconnect request for unknown client {client_id}")
    return {"message": "Client not found"}

async def cleanup(client_id: str):
    """Clean up resources for a given client."""
    logger.info(f"Cleaning up resources for client {client_id}")
    
    # Close recorder if exists
    if client_id in recorders:
        recorder = recorders.pop(client_id)
        try:
            logger.info(f"Stopping recorder for client {client_id}")
            await recorder.stop()
            logger.info(f"Recorder stopped for client {client_id}")
        except Exception as e:
            logger.error(f"Error stopping recorder for client {client_id}: {str(e)}", exc_info=True)
        
    # Close peer connection if exists
    if client_id in pcs:
        pc = pcs.pop(client_id)
        try:
            logger.info(f"Closing peer connection for client {client_id}")
            await pc.close()
            logger.info(f"Peer connection closed for client {client_id}")
        except Exception as e:
            logger.error(f"Error closing peer connection for client {client_id}: {str(e)}", exc_info=True)

@app.on_event("shutdown")
async def shutdown_event():
    """Clean up all resources when shutting down."""
    logger.info(f"Server shutting down, cleaning up {len(pcs)} connections")
    
    # Close all connections and recorders
    tasks = [cleanup(client_id) for client_id in list(pcs.keys())]
    await asyncio.gather(*tasks)
    
    logger.info("All connections closed, server shutdown complete")

if __name__ == "__main__":
    import uvicorn
    
    logger.info("Starting audio server on 0.0.0.0:8000")
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info") 