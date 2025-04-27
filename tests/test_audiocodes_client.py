"""
Unit tests for the AudioCodes WebSocket client.

These tests verify the functionality of the AudioCodesClient class,
which is responsible for connecting to AudioCodes VoiceAI Connect and
sending/receiving formatted messages.
"""

import asyncio
import base64
import json
import logging
import uuid
from unittest.mock import AsyncMock, MagicMock, patch, call

import pytest
import websockets

from app.services.websocket_client import AudioCodesClient
from app.models.message_schemas import (
    ActivitiesMessage,
    ActivityEvent,
    SessionInitiateMessage,
    UserStreamStartMessage,
    UserStreamStopMessage,
)


@pytest.fixture
def audio_client():
    """Create an AudioCodesClient instance for testing."""
    return AudioCodesClient("wss://test-audiocodes.example.com/ws")


@pytest.mark.asyncio
async def test_connect_success(audio_client):
    """Test successful connection to AudioCodes."""
    mock_ws = AsyncMock()
    
    # Add a side_effect to track if our mock is being called
    mock_connect = AsyncMock(return_value=mock_ws)
    
    # Patch at the module level where it's imported and used
    with patch("websockets.connect", mock_connect):
        # Make sure the patched function is accessible from the main module
        assert websockets.connect is mock_connect
        
        result = await audio_client.connect()
        
        # Check if our mock was called
        mock_connect.assert_called_once_with(audio_client.url)
        
        assert result is True
        assert audio_client.websocket == mock_ws


@pytest.mark.asyncio
async def test_connect_failure(audio_client):
    """Test connection failure to AudioCodes."""
    with patch("app.services.websocket_client.websockets.connect", side_effect=Exception("Connection error")):
        result = await audio_client.connect()
        
        assert result is False
        assert audio_client.websocket is None


@pytest.mark.asyncio
async def test_initiate_session_success(audio_client):
    """Test successful session initiation."""
    # Set up the mock websocket
    mock_ws = AsyncMock()
    mock_ws.recv.return_value = json.dumps({"type": "session.accepted"})
    audio_client.websocket = mock_ws
    
    # Patch uuid to return a consistent value
    mock_uuid = "test-conv-123"
    with patch("app.services.websocket_client.uuid.uuid4", return_value=mock_uuid):
        conversation_id = await audio_client.initiate_session("TestBot", "test-caller")
        
        # Verify session was initiated correctly
        assert conversation_id == str(mock_uuid)
        assert audio_client.conversation_id == str(mock_uuid)
        
        # Verify correct message was sent
        call_args = mock_ws.send.call_args[0][0]
        message = json.loads(call_args)
        assert message["type"] == "session.initiate"
        assert message["conversationId"] == str(mock_uuid)
        assert message["botName"] == "TestBot"
        assert message["caller"] == "test-caller"
        assert message["expectAudioMessages"] is True


@pytest.mark.asyncio
async def test_initiate_session_rejected(audio_client):
    """Test session initiation rejection."""
    # Set up the mock websocket
    mock_ws = AsyncMock()
    mock_ws.recv.return_value = json.dumps({"type": "session.rejected"})
    audio_client.websocket = mock_ws
    
    # Patch uuid to return a consistent value
    mock_uuid = "test-conv-123"
    with patch("app.services.websocket_client.uuid.uuid4", return_value=mock_uuid):
        conversation_id = await audio_client.initiate_session("TestBot", "test-caller")
        
        # Verify session was rejected
        assert conversation_id is None
        assert audio_client.conversation_id is None


@pytest.mark.asyncio
async def test_initiate_session_not_connected(audio_client):
    """Test session initiation when not connected."""
    audio_client.websocket = None
    
    conversation_id = await audio_client.initiate_session("TestBot", "test-caller")
    
    # Verify session was not initiated
    assert conversation_id is None


@pytest.mark.asyncio
async def test_start_user_stream_success(audio_client):
    """Test successful user stream start."""
    # Set up the mock websocket and conversation ID
    mock_ws = AsyncMock()
    mock_ws.recv.return_value = json.dumps({"type": "userStream.started"})
    audio_client.websocket = mock_ws
    audio_client.conversation_id = "test-conv-123"
    
    result = await audio_client.start_user_stream()
    
    # Verify stream was started
    assert result is True
    
    # Verify correct message was sent
    call_args = mock_ws.send.call_args[0][0]
    message = json.loads(call_args)
    assert message["type"] == "userStream.start"
    assert message["conversationId"] == "test-conv-123"


@pytest.mark.asyncio
async def test_start_user_stream_failure(audio_client):
    """Test user stream start failure."""
    # Set up the mock websocket and conversation ID
    mock_ws = AsyncMock()
    mock_ws.recv.return_value = json.dumps({"type": "error"})
    audio_client.websocket = mock_ws
    audio_client.conversation_id = "test-conv-123"
    
    result = await audio_client.start_user_stream()
    
    # Verify stream was not started
    assert result is False


@pytest.mark.asyncio
async def test_start_user_stream_not_connected(audio_client):
    """Test user stream start when not connected."""
    audio_client.websocket = None
    audio_client.conversation_id = "test-conv-123"
    
    result = await audio_client.start_user_stream()
    
    # Verify stream was not started
    assert result is False


@pytest.mark.asyncio
async def test_start_user_stream_no_session(audio_client):
    """Test user stream start with no active session."""
    audio_client.websocket = AsyncMock()
    audio_client.conversation_id = None
    
    result = await audio_client.start_user_stream()
    
    # Verify stream was not started
    assert result is False


@pytest.mark.asyncio
async def test_send_audio_chunk(audio_client):
    """Test sending audio chunk."""
    # Set up the mock websocket and conversation ID
    mock_ws = AsyncMock()
    audio_client.websocket = mock_ws
    audio_client.conversation_id = "test-conv-123"
    
    # Test audio data
    test_audio = b"test audio data"
    encoded_data = b"encoded_data"
    
    # Patch base64 to avoid external dependencies
    with patch("base64.b64encode", return_value=encoded_data):
        await audio_client.send_audio_chunk(test_audio)
        
        # Verify audio chunk was sent
        mock_ws.send.assert_called_once()
        
        # Verify correct message was sent
        call_args = mock_ws.send.call_args[0][0]
        message = json.loads(call_args)
        assert message["type"] == "userStream.chunk"
        assert message["conversationId"] == "test-conv-123"
        assert message["audioChunk"] == encoded_data.decode("utf-8")


@pytest.mark.asyncio
async def test_send_audio_chunk_not_connected(audio_client):
    """Test sending audio chunk when not connected."""
    audio_client.websocket = None
    audio_client.conversation_id = "test-conv-123"
    
    # This should not raise an exception
    await audio_client.send_audio_chunk(b"test audio data")


@pytest.mark.asyncio
async def test_send_audio_chunk_no_session(audio_client):
    """Test sending audio chunk with no active session."""
    audio_client.websocket = AsyncMock()
    audio_client.conversation_id = None
    
    # This should not raise an exception
    await audio_client.send_audio_chunk(b"test audio data")


@pytest.mark.asyncio
async def test_stop_user_stream_success(audio_client):
    """Test successful user stream stop."""
    # Set up the mock websocket and conversation ID
    mock_ws = AsyncMock()
    mock_ws.recv.return_value = json.dumps({"type": "userStream.stopped"})
    audio_client.websocket = mock_ws
    audio_client.conversation_id = "test-conv-123"
    
    result = await audio_client.stop_user_stream()
    
    # Verify stream was stopped
    assert result is True
    
    # Verify correct message was sent
    call_args = mock_ws.send.call_args[0][0]
    message = json.loads(call_args)
    assert message["type"] == "userStream.stop"
    assert message["conversationId"] == "test-conv-123"


@pytest.mark.asyncio
async def test_stop_user_stream_failure(audio_client):
    """Test user stream stop failure."""
    # Set up the mock websocket and conversation ID
    mock_ws = AsyncMock()
    mock_ws.recv.return_value = json.dumps({"type": "error"})
    audio_client.websocket = mock_ws
    audio_client.conversation_id = "test-conv-123"
    
    result = await audio_client.stop_user_stream()
    
    # Verify stream was not stopped
    assert result is False


@pytest.mark.asyncio
async def test_stop_user_stream_not_connected(audio_client):
    """Test user stream stop when not connected."""
    audio_client.websocket = None
    audio_client.conversation_id = "test-conv-123"
    
    result = await audio_client.stop_user_stream()
    
    # Verify stream was not stopped
    assert result is False


@pytest.mark.asyncio
async def test_stop_user_stream_no_session(audio_client):
    """Test user stream stop with no active session."""
    audio_client.websocket = AsyncMock()
    audio_client.conversation_id = None
    
    result = await audio_client.stop_user_stream()
    
    # Verify stream was not stopped
    assert result is False


@pytest.mark.asyncio
async def test_send_hangup(audio_client):
    """Test sending hangup activity."""
    # Set up the mock websocket and conversation ID
    mock_ws = AsyncMock()
    audio_client.websocket = mock_ws
    audio_client.conversation_id = "test-conv-123"
    
    await audio_client.send_hangup()
    
    # Verify hangup was sent
    mock_ws.send.assert_called_once()
    
    # Verify correct message was sent
    call_args = mock_ws.send.call_args[0][0]
    message = json.loads(call_args)
    assert message["type"] == "activities"
    assert message["conversationId"] == "test-conv-123"
    assert len(message["activities"]) == 1
    assert message["activities"][0]["type"] == "event"
    assert message["activities"][0]["name"] == "hangup"


@pytest.mark.asyncio
async def test_send_hangup_not_connected(audio_client):
    """Test sending hangup when not connected."""
    audio_client.websocket = None
    audio_client.conversation_id = "test-conv-123"
    
    # This should not raise an exception
    await audio_client.send_hangup()


@pytest.mark.asyncio
async def test_send_hangup_no_session(audio_client):
    """Test sending hangup with no active session."""
    audio_client.websocket = AsyncMock()
    audio_client.conversation_id = None
    
    # This should not raise an exception
    await audio_client.send_hangup()


@pytest.mark.asyncio
async def test_close(audio_client):
    """Test closing the websocket connection."""
    # Set up the mock websocket
    mock_ws = AsyncMock()
    audio_client.websocket = mock_ws
    audio_client.conversation_id = "test-conv-123"
    
    await audio_client.close()
    
    # Verify websocket was closed
    mock_ws.close.assert_called_once()
    
    # Verify state was reset
    assert audio_client.websocket is None
    assert audio_client.conversation_id is None


@pytest.mark.asyncio
async def test_close_not_connected(audio_client):
    """Test closing when not connected."""
    audio_client.websocket = None
    
    # This should not raise an exception
    await audio_client.close()


@pytest.mark.asyncio
async def test_listen(audio_client):
    """Test listening for messages."""
    # Set up the mock websocket
    mock_ws = AsyncMock()
    mock_ws.recv.side_effect = [
        json.dumps({"type": "message1"}),
        json.dumps({"type": "message2"}),
        json.dumps({"type": "session.end"}),
    ]
    audio_client.websocket = mock_ws
    
    # Create a mock message handler
    mock_handler = AsyncMock()
    
    # Run the listen method (it should exit when session.end is received)
    await audio_client.listen(mock_handler)
    
    # Verify message handler was called for each message
    assert mock_handler.call_count == 3
    mock_handler.assert_has_calls([
        call({"type": "message1"}),
        call({"type": "message2"}),
        call({"type": "session.end"})
    ])


@pytest.mark.asyncio
async def test_listen_not_connected(audio_client):
    """Test listening when not connected."""
    audio_client.websocket = None
    
    # Create a mock message handler
    mock_handler = AsyncMock()
    
    # This should not raise an exception
    await audio_client.listen(mock_handler)
    
    # Verify message handler was not called
    mock_handler.assert_not_called()


@pytest.mark.asyncio
async def test_listen_exception(audio_client):
    """Test listening with an exception."""
    # Set up the mock websocket
    mock_ws = AsyncMock()
    mock_ws.recv.side_effect = Exception("Test exception")
    audio_client.websocket = mock_ws
    
    # Create a mock message handler
    mock_handler = AsyncMock()
    
    # This should not raise an exception
    await audio_client.listen(mock_handler)
    
    # Verify message handler was not called
    mock_handler.assert_not_called() 