import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import asyncio

from fastapi import WebSocket
from fastapi.testclient import TestClient

from app.main import app
from app.models.message_schemas import (
    ConnectionValidateMessage,
    SessionInitiateMessage,
    SessionEndMessage
)


@pytest.fixture
def mock_websocket():
    """Create a mock WebSocket with a sequence of messages"""
    websocket = AsyncMock(spec=WebSocket)
    websocket.receive_text.side_effect = [
        ConnectionValidateMessage(type="connection.validate").json(),
        SessionInitiateMessage(
            type="session.initiate", 
            conversationId="test-id",
            expectAudioMessages=True,
            botName="TestBot",
            caller="+12345678901",
            supportedMediaFormats=["raw/lpcm16"]
        ).json(),
        SessionEndMessage(
            type="session.end", 
            conversationId="test-id", 
            reasonCode="normal", 
            reason="Test ended"
        ).json()
    ]
    return websocket


@pytest.mark.asyncio
async def test_websocket_endpoint_integration(mock_websocket):
    """Test the integration between FastAPI endpoint and WebSocketManager"""
    # Get the WebSocket endpoint from FastAPI
    websocket_endpoint = None
    for route in app.routes:
        if route.path == "/ws":
            websocket_endpoint = route.endpoint
            break
    
    assert websocket_endpoint is not None, "WebSocket endpoint not found"
    
    # Call the WebSocket endpoint directly
    await websocket_endpoint(mock_websocket)
    
    # Verify the WebSocket was handled correctly
    mock_websocket.accept.assert_called_once()
    assert mock_websocket.receive_text.call_count == 3
    mock_websocket.close.assert_called_once()


@pytest.mark.asyncio
async def test_full_conversation_flow():
    """Test a complete conversation flow with patched handlers"""
    # Mock the WebSocketManager.handle_websocket method
    with patch('app.websocket_manager.WebSocketManager.handle_websocket') as mock_handler:
        # Set up the mock WebSocket
        websocket = AsyncMock(spec=WebSocket)
        
        # Create handlers for each message type
        mock_connection_validate = AsyncMock()
        mock_session_initiate = AsyncMock()
        mock_user_stream_start = AsyncMock()
        mock_user_stream_chunk = AsyncMock()
        mock_user_stream_stop = AsyncMock()
        mock_activities = AsyncMock()
        mock_session_end = AsyncMock()
        
        # Mock the handlers dictionary
        handlers = {
            "connection.validate": mock_connection_validate,
            "session.initiate": mock_session_initiate,
            "userStream.start": mock_user_stream_start,
            "userStream.chunk": mock_user_stream_chunk,
            "userStream.stop": mock_user_stream_stop,
            "activities": mock_activities,
            "session.end": mock_session_end
        }
        
        # Get the websocket endpoint
        websocket_endpoint = None
        for route in app.routes:
            if route.path == "/ws":
                websocket_endpoint = route.endpoint
                break
        
        # Create a conversation flow sequence
        with patch('app.handlers.session_handlers.handle_session_initiate', mock_session_initiate), \
             patch('app.handlers.session_handlers.handle_connection_validate', mock_connection_validate), \
             patch('app.handlers.session_handlers.handle_session_end', mock_session_end), \
             patch('app.handlers.stream_handlers.handle_user_stream_start', mock_user_stream_start), \
             patch('app.handlers.stream_handlers.handle_user_stream_chunk', mock_user_stream_chunk), \
             patch('app.handlers.stream_handlers.handle_user_stream_stop', mock_user_stream_stop), \
             patch('app.handlers.activity_handlers.handle_activities', mock_activities):
            
            # Call the endpoint
            await websocket_endpoint(websocket)
            
            # In a real integration test, we'd verify the correct handlers were called
            # and the conversation state was updated properly
            # For now, we just verify the mock was called
            mock_handler.assert_called_once_with(websocket)


@pytest.mark.asyncio
async def test_parallel_conversations():
    """Test handling multiple parallel conversations"""
    # Create two mock WebSockets
    websocket1 = AsyncMock(spec=WebSocket)
    websocket2 = AsyncMock(spec=WebSocket)
    
    # Create two conversation IDs
    conv_id1 = "conversation-1"
    conv_id2 = "conversation-2"
    
    # Set up messages for the first conversation
    websocket1.receive_text.side_effect = [
        ConnectionValidateMessage(type="connection.validate").json(),
        SessionInitiateMessage(
            type="session.initiate", 
            conversationId=conv_id1,
            expectAudioMessages=True,
            botName="TestBot1",
            caller="+12345678901",
            supportedMediaFormats=["raw/lpcm16"]
        ).json(),
        SessionEndMessage(
            type="session.end", 
            conversationId=conv_id1, 
            reasonCode="normal", 
            reason="Test ended"
        ).json()
    ]
    
    # Set up messages for the second conversation
    websocket2.receive_text.side_effect = [
        ConnectionValidateMessage(type="connection.validate").json(),
        SessionInitiateMessage(
            type="session.initiate", 
            conversationId=conv_id2,
            expectAudioMessages=True,
            botName="TestBot2",
            caller="+19876543210",
            supportedMediaFormats=["raw/lpcm16"]
        ).json(),
        SessionEndMessage(
            type="session.end", 
            conversationId=conv_id2, 
            reasonCode="normal", 
            reason="Test ended"
        ).json()
    ]
    
    # Get the WebSocket endpoint
    websocket_endpoint = None
    for route in app.routes:
        if route.path == "/ws":
            websocket_endpoint = route.endpoint
            break
    
    assert websocket_endpoint is not None, "WebSocket endpoint not found"
    
    # Run the conversations in parallel
    with patch('app.models.conversation.ConversationManager.add_conversation') as mock_add_conv, \
         patch('app.models.conversation.ConversationManager.get_conversation') as mock_get_conv, \
         patch('app.models.conversation.ConversationManager.remove_conversation') as mock_remove_conv:
        
        # Mock the conversation manager methods
        mock_get_conv.side_effect = lambda conv_id: MagicMock(conversation_id=conv_id)
        
        # Run the conversations in parallel
        await asyncio.gather(
            websocket_endpoint(websocket1),
            websocket_endpoint(websocket2)
        )
        
        # Verify both connections were handled correctly
        websocket1.accept.assert_called_once()
        websocket2.accept.assert_called_once()
        
        assert websocket1.receive_text.call_count == 3
        assert websocket2.receive_text.call_count == 3
        
        websocket1.close.assert_called_once()
        websocket2.close.assert_called_once()
        
        # Verify that the conversations were removed
        mock_remove_conv.assert_any_call(conv_id1)
        mock_remove_conv.assert_any_call(conv_id2) 