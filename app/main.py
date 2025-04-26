"""
FastAPI server for AudioCodes VoiceAI Connect real-time voice agent integration.

This module initializes and configures the FastAPI application that serves as
the webhook endpoint for AudioCodes VoiceAI Connect Enterprise platform. It
implements the WebSocket protocol defined by the AudioCodes Bot API to enable
real-time voice interactions between users and AI voice agents.

The server handles incoming WebSocket connections, routes messages to appropriate
handlers, and maintains conversation state throughout the call session.
"""

from fastapi import FastAPI, WebSocket

from app.config.logging_config import configure_logging
from app.websocket_manager import WebSocketManager

# Configure logging
logger = configure_logging()

# Create FastAPI application
app = FastAPI()

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
    return {"status": "healthy"}


if __name__ == "__main__":
    import uvicorn

    logger.info("Starting AC Server on http://0.0.0.0:8000")
    uvicorn.run(app, host="0.0.0.0", port=8000)
