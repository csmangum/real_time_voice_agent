import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import WebSocket

from app.websocket_manager import WebSocketManager
from app.models.conversation import ConversationManager

@pytest.fixture
def websocket_manager():
    return WebSocketManager()

@pytest.fixture
def websocket():
    websocket = AsyncMock(spec=WebSocket)
    # Mock the receive_text method to return different messages on consecutive calls
    websocket.receive_text.side_effect = [
        json.dumps({"type": "connection.validate"}),
        json.dumps({"type": "session.initiate", "conversationId": "test-id", "supportedMediaFormats": ["raw/lpcm16"]}),
        json.dumps({"type": "session.end", "conversationId": "test-id"})
    ]
    return websocket

@pytest.mark.asyncio
async def test_websocket_manager_initialization(websocket_manager):
    """Test that WebSocketManager initializes correctly"""
    assert isinstance(websocket_manager.conversation_manager, ConversationManager)
    assert len(websocket_manager.handlers) == 8  # Assuming there are 8 handlers
    assert "session.initiate" in websocket_manager.handlers
    assert "session.resume" in websocket_manager.handlers
    assert "userStream.start" in websocket_manager.handlers
    assert "userStream.chunk" in websocket_manager.handlers
    assert "userStream.stop" in websocket_manager.handlers
    assert "activities" in websocket_manager.handlers
    assert "session.end" in websocket_manager.handlers
    assert "connection.validate" in websocket_manager.handlers

@pytest.mark.asyncio
async def test_handle_websocket_flow(websocket_manager, websocket):
    """Test the full flow of handling a websocket connection"""
    # Create mocked handlers
    connection_validate_handler = AsyncMock(return_value={"type": "connection.validated", "success": True})
    session_initiate_handler = AsyncMock(return_value={"type": "session.accepted", "mediaFormat": "raw/lpcm16"})
    session_end_handler = AsyncMock(return_value=None)
    
    # Mock handlers dictionary
    websocket_manager.handlers = {
        "connection.validate": connection_validate_handler,
        "session.initiate": session_initiate_handler,
        "session.end": session_end_handler
    }
    
    # Handle websocket connection
    await websocket_manager.handle_websocket(websocket)
    
    # Assert websocket was accepted
    websocket.accept.assert_called_once()
    
    # Assert websocket.receive_text was called 3 times (for our 3 messages)
    assert websocket.receive_text.call_count == 3
    
    # Assert handlers were called with correct parameters
    connection_validate_handler.assert_called_once()
    session_initiate_handler.assert_called_once()
    session_end_handler.assert_called_once()
    
    # Assert websocket was closed at the end
    websocket.close.assert_called_once()

@pytest.mark.asyncio
async def test_handle_websocket_exception(websocket_manager):
    """Test that exceptions are handled properly"""
    # Create a websocket that raises an exception
    websocket = AsyncMock(spec=WebSocket)
    websocket.receive_text.side_effect = Exception("Test exception")
    
    # Handle websocket connection (should not raise)
    await websocket_manager.handle_websocket(websocket)
    
    # Assert websocket was accepted and then closed
    websocket.accept.assert_called_once()
    websocket.close.assert_called_once()

@pytest.mark.asyncio
async def test_handle_unhandled_message_type(websocket_manager):
    """Test handling of unrecognized message types"""
    # Create a websocket with an unknown message type
    websocket = AsyncMock(spec=WebSocket)
    websocket.receive_text.side_effect = [
        json.dumps({"type": "unknown.message.type", "conversationId": "test-id"}),
        json.dumps({"type": "session.end", "conversationId": "test-id"})
    ]
    
    # Handle websocket connection
    await websocket_manager.handle_websocket(websocket)
    
    # Assert websocket was accepted and then closed
    websocket.accept.assert_called_once()
    websocket.close.assert_called_once()
    
    # Assert no response was sent for the unknown message type
    # (The call count should be 0 since we mocked all handlers)
    assert websocket.send_text.call_count == 0 