"""
Unit tests for the OpenAI Realtime API client.

These tests verify the functionality of the RealtimeAudioClient class,
which is responsible for connecting to the OpenAI Realtime API and
streaming audio data.
"""

import asyncio
import json
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import websockets
from websockets.exceptions import ConnectionClosedError

from app.bot.realtime_api import RealtimeAudioClient


@pytest.fixture
def mock_api_key():
    """Provide a mock API key for testing."""
    return "test-api-key"


@pytest.fixture
def mock_model():
    """Provide a mock model name for testing."""
    return "gpt-4o-realtime-preview-test"


@pytest.fixture
def realtime_client(mock_api_key, mock_model):
    """Create a RealtimeAudioClient instance for testing."""
    return RealtimeAudioClient(mock_api_key, mock_model)


@pytest.mark.asyncio
async def test_connect_success(realtime_client):
    """Test successful connection to the OpenAI Realtime API."""
    mock_ws = AsyncMock()
    
    with patch("websockets.connect", return_value=mock_ws):
        with patch("asyncio.wait_for", return_value=mock_ws) as mock_wait_for:
            with patch("asyncio.create_task") as mock_create_task:
                result = await realtime_client.connect()
                
                assert result is True
                assert realtime_client.ws == mock_ws
                assert realtime_client._connection_active is True
                assert mock_create_task.call_count == 2  # _recv_loop and _heartbeat


@pytest.mark.asyncio
async def test_connect_failure(realtime_client):
    """Test connection failure to the OpenAI Realtime API."""
    with patch("websockets.connect", side_effect=Exception("Connection error")):
        result = await realtime_client.connect()
        
        assert result is False
        assert realtime_client._connection_active is False


@pytest.mark.asyncio
async def test_send_audio_chunk_success(realtime_client):
    """Test sending an audio chunk successfully."""
    realtime_client.ws = AsyncMock()
    realtime_client._connection_active = True
    realtime_client.ws.closed = False
    
    mock_chunk = b"test audio data"
    result = await realtime_client.send_audio_chunk(mock_chunk)
    
    assert result is True
    realtime_client.ws.send.assert_called_once_with(mock_chunk)


@pytest.mark.asyncio
async def test_send_audio_chunk_connection_closed(realtime_client):
    """Test sending an audio chunk when connection is closed."""
    realtime_client.ws = AsyncMock()
    realtime_client.ws.send.side_effect = ConnectionClosedError(None, None)
    realtime_client._connection_active = True
    
    with patch.object(realtime_client, "reconnect", return_value=False):
        mock_chunk = b"test audio data"
        result = await realtime_client.send_audio_chunk(mock_chunk)
        
        assert result is False


@pytest.mark.asyncio
async def test_receive_audio_chunk(realtime_client):
    """Test receiving an audio chunk."""
    mock_chunk = b"received audio data"
    
    # Put the mock chunk in the queue
    await realtime_client.audio_queue.put(mock_chunk)
    
    # Check that receive_audio_chunk returns the chunk
    result = await realtime_client.receive_audio_chunk()
    assert result == mock_chunk


@pytest.mark.asyncio
async def test_reconnect(realtime_client):
    """Test reconnection logic."""
    # Mock successful connection
    with patch.object(realtime_client, "connect", return_value=True):
        result = await realtime_client.reconnect()
        
        assert result is True
        assert realtime_client._reconnect_attempts == 1
    
    # Reset reconnect attempts
    realtime_client._reconnect_attempts = 0
    
    # Test max reconnect attempts
    realtime_client._reconnect_attempts = 5  # MAX_RECONNECT_ATTEMPTS
    result = await realtime_client.reconnect()
    
    assert result is False


@pytest.mark.asyncio
async def test_close(realtime_client):
    """Test closing the client."""
    realtime_client.ws = AsyncMock()
    realtime_client._recv_task = AsyncMock()
    realtime_client._heartbeat_task = AsyncMock()
    
    await realtime_client.close()
    
    assert realtime_client._is_closing is True
    assert realtime_client._connection_active is False
    realtime_client._recv_task.cancel.assert_called_once()
    realtime_client._heartbeat_task.cancel.assert_called_once()
    realtime_client.ws.close.assert_called_once() 