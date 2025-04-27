"""
Unit tests for the AudioCodes Realtime Bridge.

These tests verify the functionality of the AudiocodesRealtimeBridge class,
which connects AudioCodes WebSocket protocol with OpenAI Realtime API.
"""

import asyncio
import base64
import json
import os
from unittest.mock import AsyncMock, MagicMock, patch, call

import pytest
from fastapi import WebSocket

from app.bot.audiocodes_realtime_bridge import AudiocodesRealtimeBridge
from app.bot.realtime_api import RealtimeAudioClient
import app.bot.audiocodes_realtime_bridge as bridge_module


@pytest.fixture
def mock_websocket():
    """Create a mock WebSocket for testing."""
    mock = AsyncMock(spec=WebSocket)
    return mock


@pytest.fixture
def mock_client():
    """Create a mock RealtimeAudioClient for testing."""
    mock = AsyncMock(spec=RealtimeAudioClient)
    mock.connect.return_value = True
    return mock


@pytest.fixture
def bridge():
    """Create an AudiocodesRealtimeBridge instance for testing."""
    return AudiocodesRealtimeBridge()


@pytest.mark.asyncio
@patch.object(RealtimeAudioClient, '__init__', return_value=None)
@patch.object(RealtimeAudioClient, 'connect')
@patch('asyncio.create_task')
async def test_create_client(mock_create_task, mock_connect, mock_init, bridge, mock_websocket):
    """Test creating a new client."""
    conversation_id = "test-conv-123"
    
    # Set environment variable for test
    with patch.dict(os.environ, {"OPENAI_API_KEY": "test-api-key"}):
        with patch.object(bridge_module, 'OPENAI_API_KEY', 'test-api-key'):
            await bridge.create_client(conversation_id, mock_websocket)
    
    # Verify RealtimeAudioClient was created and connected
    mock_init.assert_called_once()
    mock_connect.assert_called_once()
    
    # Verify client was stored in bridge
    assert conversation_id in bridge.clients
    assert bridge.websockets[conversation_id] == mock_websocket
    assert bridge.stream_ids[conversation_id] == 1
    
    # Verify response handling task was created
    mock_create_task.assert_called_once()


@pytest.mark.asyncio
async def test_create_client_no_api_key(bridge, mock_websocket):
    """Test creating a client without API key set."""
    conversation_id = "test-conv-123"
    
    # Directly patch the module-level OPENAI_API_KEY variable
    with patch.object(bridge_module, 'OPENAI_API_KEY', None):
        with pytest.raises(ValueError, match="OPENAI_API_KEY environment variable not set"):
            await bridge.create_client(conversation_id, mock_websocket)


@pytest.mark.asyncio
async def test_send_audio_chunk(bridge, mock_client):
    """Test sending an audio chunk to OpenAI."""
    conversation_id = "test-conv-123"
    audio_chunk = base64.b64encode(b"test audio data").decode("utf-8")
    
    # Mock client in the bridge
    bridge.clients[conversation_id] = mock_client
    
    await bridge.send_audio_chunk(conversation_id, audio_chunk)
    
    # Verify audio was sent to the client
    mock_client.send_audio_chunk.assert_called_once_with(b"test audio data")


@pytest.mark.asyncio
async def test_send_audio_chunk_no_client(bridge):
    """Test sending audio with no client for the conversation."""
    conversation_id = "nonexistent"
    audio_chunk = base64.b64encode(b"test audio data").decode("utf-8")
    
    # This should not raise an exception
    await bridge.send_audio_chunk(conversation_id, audio_chunk)


class MockWebSocket:
    """A simple websocket mock that records sent messages."""
    def __init__(self, *args, **kwargs):
        self.sent_messages = []
    
    async def send_text(self, text):
        """Record the sent message."""
        self.sent_messages.append(text)
        return None


@pytest.mark.asyncio
async def test_handle_openai_responses(bridge, mock_client):
    """Test handling audio responses from OpenAI."""
    conversation_id = "test-conv-123"
    stream_id = 1
    
    # Create a proper mock WebSocket
    mock_websocket = MockWebSocket()
    
    # Setup the test
    bridge.clients[conversation_id] = mock_client
    bridge.websockets[conversation_id] = mock_websocket
    bridge.stream_ids[conversation_id] = stream_id
    
    # Mock client receiving audio chunks - we'll use a list that allows us to control the flow
    chunks = [b"audio chunk 1", b"audio chunk 2"]
    
    # Create a custom receive_audio_chunk method that returns our chunks then raises CancelledError
    async def mock_receive_audio_chunk():
        if chunks:
            return chunks.pop(0)
        raise asyncio.CancelledError()
    
    mock_client.receive_audio_chunk = mock_receive_audio_chunk
    
    # Run the response handler
    await bridge._handle_openai_responses(conversation_id)
    
    # Verify messages were sent
    assert len(mock_websocket.sent_messages) >= 3  # start, 2 chunks, stop
    
    # Verify playStream.start message was sent
    start_message = json.dumps({
        "type": "playStream.start",
        "streamId": str(stream_id),
        "mediaFormat": "raw/lpcm16"
    })
    assert start_message in mock_websocket.sent_messages
    
    # Verify audio chunks were sent
    chunk1_message = json.dumps({
        "type": "playStream.chunk",
        "streamId": str(stream_id),
        "audioChunk": base64.b64encode(b"audio chunk 1").decode("utf-8")
    })
    assert chunk1_message in mock_websocket.sent_messages
    
    chunk2_message = json.dumps({
        "type": "playStream.chunk",
        "streamId": str(stream_id),
        "audioChunk": base64.b64encode(b"audio chunk 2").decode("utf-8")
    })
    assert chunk2_message in mock_websocket.sent_messages
    
    # Verify playStream.stop was sent at the end
    stop_message = json.dumps({
        "type": "playStream.stop",
        "streamId": str(stream_id)
    })
    assert stop_message in mock_websocket.sent_messages


@pytest.mark.asyncio
async def test_handle_openai_responses_missing_components(bridge):
    """Test handling responses with missing client or websocket."""
    conversation_id = "missing"
    
    # This should not raise an exception but return early
    await bridge._handle_openai_responses(conversation_id)


@pytest.mark.asyncio
async def test_stop_stream(bridge):
    """Test stopping an audio stream."""
    conversation_id = "test-conv-123"
    stream_id = 2
    
    # Create a proper mock WebSocket
    mock_websocket = MockWebSocket()
    
    # Setup test
    bridge.websockets[conversation_id] = mock_websocket
    bridge.stream_ids[conversation_id] = stream_id
    
    await bridge.stop_stream(conversation_id)
    
    # Verify stop message was sent
    expected_message = json.dumps({
        "type": "playStream.stop",
        "streamId": str(stream_id)
    })
    assert expected_message in mock_websocket.sent_messages
    assert len(mock_websocket.sent_messages) == 1  # Only one message sent


@pytest.mark.asyncio
async def test_stop_stream_no_websocket(bridge):
    """Test stopping a stream with no websocket."""
    conversation_id = "nonexistent"
    
    # This should not raise an exception
    await bridge.stop_stream(conversation_id)


@pytest.mark.asyncio
async def test_close_client(bridge, mock_client):
    """Test closing a client."""
    conversation_id = "test-conv-123"
    
    # Setup test
    bridge.clients[conversation_id] = mock_client
    bridge.websockets[conversation_id] = MagicMock()
    bridge.stream_ids[conversation_id] = 1
    
    await bridge.close_client(conversation_id)
    
    # Verify client was closed
    mock_client.close.assert_called_once()
    
    # Verify client was removed from dictionaries
    assert conversation_id not in bridge.clients
    assert conversation_id not in bridge.websockets
    assert conversation_id not in bridge.stream_ids


@pytest.mark.asyncio
async def test_close_client_nonexistent(bridge):
    """Test closing a nonexistent client."""
    conversation_id = "nonexistent"
    
    # This should not raise an exception
    await bridge.close_client(conversation_id) 