import logging
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
    """WebSocket endpoint for real-time communication"""
    await websocket_manager.handle_websocket(websocket)

@app.get("/health")
async def health_check():
    """Simple health check endpoint"""
    return {"status": "healthy"}

if __name__ == "__main__":
    import uvicorn
    
    logger.info("Starting AC Server on http://0.0.0.0:8000")
    uvicorn.run(app, host="0.0.0.0", port=8000) 