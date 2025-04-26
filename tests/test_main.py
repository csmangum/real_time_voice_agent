import pytest
from fastapi.testclient import TestClient

from app.main import app, websocket_manager

client = TestClient(app)

def test_health_check():
    """Test the health check endpoint returns correct response"""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}
    
def test_websocket_endpoint_initialization():
    """Test that websocket_manager is properly initialized"""
    # Verify that the WebSocketManager instance exists
    assert websocket_manager is not None
    # Verify that the conversation manager is initialized
    assert websocket_manager.conversation_manager is not None
    # Verify that handlers are set up
    assert len(websocket_manager.handlers) > 0
    assert "session.initiate" in websocket_manager.handlers
    assert "userStream.start" in websocket_manager.handlers
    assert "activities" in websocket_manager.handlers 