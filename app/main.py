"""
FastAPI server for AudioCodes VoiceAI Connect real-time voice agent integration.

This module initializes and configures the FastAPI application that serves as
the webhook endpoint for AudioCodes VoiceAI Connect Enterprise platform. It
implements the WebSocket protocol defined by the AudioCodes Bot API to enable
real-time voice interactions between users and AI voice agents.

The server handles incoming WebSocket connections, routes messages to appropriate
handlers, and maintains conversation state throughout the call session.
"""

import os
from pathlib import Path

import dotenv
from fastapi import FastAPI, WebSocket

from app.config.logging_config import configure_logging
from app.websocket_manager import WebSocketManager

# Load environment variables from .env file if it exists
env_path = Path(".") / ".env"
if env_path.exists():
    dotenv.load_dotenv(env_path)

# Configure logging
logger = configure_logging()

# Get configuration from environment variables
PORT = int(os.getenv("PORT", "8000"))
HOST = os.getenv("HOST", "0.0.0.0")

# Create FastAPI application
app = FastAPI(
    title="Real-Time Voice Agent",
    description="Integration between AudioCodes VoiceAI Connect and OpenAI Realtime API",
    version="1.0.0",
)

# Create WebSocket manager
websocket_manager = WebSocketManager()


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for real-time communication with AudioCodes VoiceAI Connect.

    This endpoint handles the complete WebSocket lifecycle for voice bot communications:
    - WebSocket connection establishment and authentication
    - Message routing for session management (initiate, resume, end)
    - Audio streaming (start, chunk, stop)
    - Activity handling (DTMF, speech recognition, etc.)

    All messages follow the AudioCodes Bot API WebSocket protocol format.
    """
    await websocket_manager.handle_websocket(websocket)


@app.get("/health")
async def health_check():
    """Health check endpoint for monitoring system status.

    Returns:
        dict: Status information indicating the server is operational.

    This endpoint can be used by load balancers or monitoring tools
    to verify the service is running and responsive.
    """
    return {"status": "healthy", "openai_api_key_configured": bool(os.getenv("OPENAI_API_KEY"))}


@app.get("/")
async def root():
    """Root endpoint to display basic information about the API.

    Returns:
        dict: Basic information about the API and its purpose.
    """
    return {
        "name": "Real-Time Voice Agent",
        "description": "Integration between AudioCodes VoiceAI Connect and OpenAI Realtime API",
        "version": "1.0.0",
        "endpoints": {
            "/ws": "WebSocket endpoint for AudioCodes VoiceAI Connect",
            "/health": "Health check endpoint",
        },
    }


if __name__ == "__main__":
    import uvicorn

    logger.info(f"Starting server on http://{HOST}:{PORT}")
    uvicorn.run(app, host=HOST, port=PORT)
