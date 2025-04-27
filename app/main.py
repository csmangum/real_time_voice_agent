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
import statistics
from pathlib import Path

import dotenv
from fastapi import FastAPI, WebSocket

from app.config.logging_config import configure_logging
from app.websocket_manager import WebSocketManager
from app.bot.audiocodes_realtime_bridge import bridge

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
        dict: Status information indicating the server is operational, including latency metrics.

    This endpoint can be used by load balancers or monitoring tools
    to verify the service is running and responsive.
    """
    # Get latency metrics from the bridge
    latency_metrics = {}
    if bridge and hasattr(bridge, "audio_latencies") and bridge.audio_latencies:
        latencies = list(bridge.audio_latencies.values())
        if latencies:
            latency_metrics = {
                "latency_ms": {
                    "avg": statistics.mean(latencies),
                    "min": min(latencies),
                    "max": max(latencies),
                    "median": statistics.median(latencies),
                }
            }
            if len(latencies) > 1:
                latency_metrics["latency_ms"]["std_dev"] = statistics.stdev(latencies)
    
    # Count active connections
    active_connections = 0
    if bridge and hasattr(bridge, "clients"):
        active_connections = len(bridge.clients)
    
    return {
        "status": "healthy", 
        "openai_api_key_configured": bool(os.getenv("OPENAI_API_KEY")),
        "active_connections": active_connections,
        **latency_metrics
    }


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
    # Configure uvicorn with low buffer sizes for minimal latency
    uvicorn.run(
        app, 
        host=HOST, 
        port=PORT,
        # Low write buffer size to minimize buffering and reduce latency
        # This ensures WebSocket messages are sent as soon as possible
        websocket_ping_interval=5,  # More frequent pings to keep connections alive
        websocket_max_size=16777216,  # 16MB - large enough for audio chunks
        websocket_ping_timeout=20,  # Timeout for pings to detect dead connections
        # Use HTTP/1.1 for lower overhead than HTTP/2
        http="h11"
    )
