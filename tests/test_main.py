import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock

from app.main import app, websocket_manager

client = TestClient(app)

def test_health_check():
    """Test the health check endpoint returns correct response"""
    response = client.get("/health")
    assert response.status_code == 200
    
    response_json = response.json()
    assert response_json["status"] == "healthy"
    assert "openai_api_key_configured" in response_json
    assert isinstance(response_json["openai_api_key_configured"], bool)

def test_root_endpoint():
    """Test the root endpoint returns the correct API information"""
    response = client.get("/")
    assert response.status_code == 200
    
    response_json = response.json()
    assert response_json["name"] == "Real-Time Voice Agent"
    assert "description" in response_json
    assert response_json["version"] == "1.0.0"
    assert "endpoints" in response_json
    assert "/ws" in response_json["endpoints"]
    assert "/health" in response_json["endpoints"]
    
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

@pytest.mark.asyncio
async def test_websocket_endpoint():
    """Test that websocket endpoint calls the handle_websocket method"""
    with patch('app.websocket_manager.WebSocketManager.handle_websocket') as mock_handle:
        # This is a limited test as we can't easily test WebSockets with TestClient
        # In a real scenario, we'd use something like websockets library for a more comprehensive test
        mock_handle.return_value = None
        mock_websocket = MagicMock()
        
        # Find the websocket endpoint by path
        websocket_route = next(route for route in app.routes if route.path == "/ws")
        websocket_endpoint = websocket_route.endpoint
        await websocket_endpoint(mock_websocket)
        
        # Verify the websocket is handled
        mock_handle.assert_called_once_with(mock_websocket)

@pytest.mark.asyncio
async def test_app_startup_configuration():
    """Test the app configuration on startup"""
    # Check that FastAPI app is configured correctly
    assert app.title == "Real-Time Voice Agent"
    assert "AudioCodes" in app.description
    assert app.version == "1.0.0"
    
    # Check routes are set up correctly
    route_paths = [route.path for route in app.routes]
    assert "/ws" in route_paths
    assert "/health" in route_paths
    assert "/" in route_paths 