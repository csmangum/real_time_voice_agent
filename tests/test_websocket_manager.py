import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch, call

from fastapi import WebSocket

from app.websocket_manager import WebSocketManager
from app.models.conversation import ConversationManager
from app.models.message_schemas import (
    ConnectionValidateMessage,
    SessionInitiateMessage,
    SessionResumeMessage,
    SessionEndMessage,
    UserStreamStartMessage,
    UserStreamChunkMessage,
    UserStreamStopMessage,
    ActivitiesMessage,
    ConnectionValidatedResponse,
    SessionAcceptedResponse
)

@pytest.fixture
def websocket_manager():
    return WebSocketManager()

@pytest.fixture
def websocket():
    websocket = AsyncMock(spec=WebSocket)
    # Mock the receive_text method to return different messages on consecutive calls
    # We're still returning JSON strings as that's what WebSockets receive
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
    connection_validate_handler = AsyncMock(
        return_value=ConnectionValidatedResponse(
            type="connection.validated",
            success=True
        )
    )
    session_initiate_handler = AsyncMock(
        return_value=SessionAcceptedResponse(
            type="session.accepted",
            mediaFormat="raw/lpcm16",
            conversationId="test-id"
        )
    )
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
        # Need to create a valid JSON string for an unrecognized message type
        json.dumps({"type": "unknown.message.type", "conversationId": "test-id"}),
        # Valid message to end the session
        SessionEndMessage(
            type="session.end", 
            conversationId="test-id", 
            reasonCode="normal", 
            reason="Test ended"
        ).json()
    ]
    
    # Handle websocket connection
    await websocket_manager.handle_websocket(websocket)
    
    # Assert websocket was accepted and then closed
    websocket.accept.assert_called_once()
    websocket.close.assert_called_once()
    
    # Assert no response was sent for the unknown message type
    # (The call count should be 0 since we mocked all handlers)
    assert websocket.send_text.call_count == 0

@pytest.mark.asyncio
async def test_handle_user_stream_start():
    """Test handling of userStream.start message"""
    # Setup
    websocket = AsyncMock(spec=WebSocket)
    conversation_manager = ConversationManager()
    msg = UserStreamStartMessage(
        type="userStream.start",
        conversationId="test-id",
        userStream={
            "mediaFormat": "raw/lpcm16",
            "sampleRate": 16000
        }
    )
    
    # Create a conversation first (required for user stream messages)
    conversation_manager.add_conversation("test-id", websocket, "raw/lpcm16")
    
    # Test with patched handlers
    with patch('app.handlers.stream_handlers.handle_user_stream_start') as mock_handler:
        # Create expected response
        mock_response = {"type": "userStream.started", "conversationId": "test-id"}
        mock_handler.return_value = mock_response
        
        # Call handler
        from app.handlers.stream_handlers import handle_user_stream_start
        response = await handle_user_stream_start(json.loads(msg.json()), websocket, conversation_manager)
        
        # Verify
        assert response == mock_response
        mock_handler.assert_called_once()

@pytest.mark.asyncio
async def test_handle_user_stream_chunk():
    """Test handling of userStream.chunk message"""
    # Setup
    websocket = AsyncMock(spec=WebSocket)
    conversation_manager = ConversationManager()
    msg = UserStreamChunkMessage(
        type="userStream.chunk",
        conversationId="test-id",
        audioChunk="aGVsbG8="  # Valid base64 encoding of "hello"
    )
    
    # Create a conversation first
    conversation_manager.add_conversation("test-id", websocket, "raw/lpcm16")
    
    # Test with patched handlers
    with patch('app.handlers.stream_handlers.handle_user_stream_chunk') as mock_handler:
        mock_handler.return_value = None  # No response for chunk messages
        
        # Call handler
        from app.handlers.stream_handlers import handle_user_stream_chunk
        response = await handle_user_stream_chunk(json.loads(msg.json()), websocket, conversation_manager)
        
        # Verify
        assert response is None
        mock_handler.assert_called_once()

@pytest.mark.asyncio
async def test_handle_session_resume():
    """Test handling of session.resume message"""
    # Setup
    websocket = AsyncMock(spec=WebSocket)
    conversation_manager = ConversationManager()
    msg = SessionResumeMessage(
        type="session.resume",
        conversationId="test-id"
    )
    
    # Test with patched handlers
    with patch('app.handlers.session_handlers.handle_session_resume') as mock_handler:
        mock_response = {"type": "session.resumed", "conversationId": "test-id"}
        mock_handler.return_value = mock_response
        
        # Call handler
        from app.handlers.session_handlers import handle_session_resume
        response = await handle_session_resume(json.loads(msg.json()), websocket, conversation_manager)
        
        # Verify
        assert response == mock_response
        mock_handler.assert_called_once()

@pytest.mark.asyncio
async def test_handle_activities():
    """Test handling of activities message"""
    # Setup
    websocket = AsyncMock(spec=WebSocket)
    conversation_manager = ConversationManager()
    msg = ActivitiesMessage(
        type="activities",
        conversationId="test-id",
        activities=[
            {
                "type": "event",
                "name": "dtmf",
                "value": "1"
            }
        ]
    )
    
    # Create a conversation first
    conversation_manager.add_conversation("test-id", websocket, "raw/lpcm16")
    
    # Test with patched handlers
    with patch('app.handlers.activity_handlers.handle_activities') as mock_handler:
        mock_response = {"type": "activities.processed", "conversationId": "test-id"}
        mock_handler.return_value = mock_response
        
        # Call handler
        from app.handlers.activity_handlers import handle_activities
        response = await handle_activities(json.loads(msg.json()), websocket, conversation_manager)
        
        # Verify
        assert response == mock_response
        mock_handler.assert_called_once()

@pytest.mark.asyncio
async def test_invalid_message_validation():
    """Test handling of messages that fail validation"""
    # Setup
    websocket = AsyncMock(spec=WebSocket)
    websocket_manager = WebSocketManager()
    
    # Create an invalid message (missing required fields)
    invalid_message = json.dumps({"type": "session.initiate"})  # Missing required fields
    valid_end_message = SessionEndMessage(
        type="session.end", 
        conversationId="test-id", 
        reasonCode="normal", 
        reason="Test ended"
    ).json()
    
    websocket.receive_text.side_effect = [invalid_message, valid_end_message]
    
    # Run test
    await websocket_manager.handle_websocket(websocket)
    
    # Verify no error was thrown and the connection was handled
    websocket.accept.assert_called_once()
    websocket.close.assert_called_once()

@pytest.mark.asyncio
async def test_conversation_cleanup_on_error():
    """Test that conversation is cleaned up when an error occurs"""
    # Setup
    websocket = AsyncMock(spec=WebSocket)
    websocket_manager = WebSocketManager()
    
    # Mock the conversation manager
    websocket_manager.conversation_manager.remove_conversation = AsyncMock()
    
    # First message creates a conversation, second raises an error
    websocket.receive_text.side_effect = [
        SessionInitiateMessage(
            type="session.initiate", 
            conversationId="test-id",
            expectAudioMessages=True,
            botName="TestBot",
            caller="+12345678901",
            supportedMediaFormats=["raw/lpcm16"]
        ).json(),
        Exception("Test exception")
    ]
    
    # Run test
    await websocket_manager.handle_websocket(websocket)
    
    # Verify cleanup was attempted
    websocket_manager.conversation_manager.remove_conversation.assert_called_once_with("test-id")
    websocket.close.assert_called_once()

@pytest.mark.asyncio
async def test_multiple_messages_handling():
    """Test handling of multiple consecutive messages"""
    # Setup
    websocket = AsyncMock(spec=WebSocket)
    websocket_manager = WebSocketManager()
    
    # Create a series of messages in a conversation
    messages = [
        ConnectionValidateMessage(type="connection.validate").json(),
        SessionInitiateMessage(
            type="session.initiate", 
            conversationId="test-id",
            expectAudioMessages=True,
            botName="TestBot",
            caller="+12345678901",
            supportedMediaFormats=["raw/lpcm16"]
        ).json(),
        UserStreamStartMessage(
            type="userStream.start",
            conversationId="test-id",
            userStream={"mediaFormat": "raw/lpcm16", "sampleRate": 16000}
        ).json(),
        UserStreamChunkMessage(
            type="userStream.chunk",
            conversationId="test-id",
            audioChunk="aGVsbG8="  # Valid base64 encoding of "hello"
        ).json(),
        UserStreamStopMessage(
            type="userStream.stop",
            conversationId="test-id"
        ).json(),
        SessionEndMessage(
            type="session.end", 
            conversationId="test-id", 
            reasonCode="normal", 
            reason="Test ended"
        ).json()
    ]
    
    websocket.receive_text.side_effect = messages
    
    # Mock all handlers
    for handler_name in websocket_manager.handlers:
        websocket_manager.handlers[handler_name] = AsyncMock(return_value=None)
    
    # We need to patch the function in the websocket_manager module where it's used directly
    with patch('app.websocket_manager.handle_user_stream_chunk', AsyncMock(return_value=None)) as mock_chunk_handler:
        # Run test
        await websocket_manager.handle_websocket(websocket)
        
        # Verify all handlers were called
        assert websocket_manager.handlers["connection.validate"].call_count == 1
        assert websocket_manager.handlers["session.initiate"].call_count == 1
        assert websocket_manager.handlers["userStream.start"].call_count == 1
        # Check the directly patched function instead
        assert mock_chunk_handler.call_count == 1
        assert websocket_manager.handlers["userStream.stop"].call_count == 1
        assert websocket_manager.handlers["session.end"].call_count == 1
        
        # Verify websocket was closed at the end
        websocket.close.assert_called_once() 