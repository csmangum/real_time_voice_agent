import unittest
import json
import base64
from unittest.mock import AsyncMock, patch, MagicMock
import pytest

from app.handlers.stream_handlers import (
    handle_user_stream_start,
    handle_user_stream_chunk,
    handle_user_stream_stop,
    send_play_stream
)
from app.models.conversation import ConversationManager

@pytest.mark.asyncio
class TestStreamHandlers:
    
    async def test_handle_user_stream_start(self):
        # Setup
        websocket = AsyncMock()
        conversation_manager = MagicMock(spec=ConversationManager)
        message = {"conversationId": "test-conversation-id"}
        
        # Execute
        response = await handle_user_stream_start(message, websocket, conversation_manager)
        
        # Assert
        assert response == {"type": "userStream.started"}
    
    async def test_handle_user_stream_chunk(self):
        # Setup
        websocket = AsyncMock()
        conversation_manager = MagicMock(spec=ConversationManager)
        # Base64 encoded sample audio chunk
        audio_chunk = base64.b64encode(b"test_audio_data").decode("utf-8")
        message = {
            "conversationId": "test-conversation-id",
            "audioChunk": audio_chunk
        }
        
        # Execute
        response = await handle_user_stream_chunk(message, websocket, conversation_manager)
        
        # Assert
        assert response is None
    
    async def test_handle_user_stream_stop(self):
        # Setup
        websocket = AsyncMock()
        conversation_manager = MagicMock(spec=ConversationManager)
        message = {"conversationId": "test-conversation-id"}
        
        # Execute
        response = await handle_user_stream_stop(message, websocket, conversation_manager)
        
        # Assert
        assert response == {"type": "userStream.stopped"}
    
    async def test_send_play_stream(self):
        # Setup
        websocket = AsyncMock()
        stream_id = "test-stream-id"
        media_format = "raw/lpcm16"
        audio_data = b"test_audio_data"
        
        # Execute
        await send_play_stream(websocket, stream_id, media_format, audio_data)
        
        # Assert
        # Check that the websocket send_text method was called 3 times
        assert websocket.send_text.call_count == 3
        
        # Check the first call (playStream.start)
        first_call_args = websocket.send_text.call_args_list[0][0][0]
        first_call_json = json.loads(first_call_args)
        assert first_call_json["type"] == "playStream.start"
        assert first_call_json["streamId"] == stream_id
        assert first_call_json["mediaFormat"] == media_format
        
        # Check the second call (playStream.chunk)
        second_call_args = websocket.send_text.call_args_list[1][0][0]
        second_call_json = json.loads(second_call_args)
        assert second_call_json["type"] == "playStream.chunk"
        assert second_call_json["streamId"] == stream_id
        assert second_call_json["audioChunk"] == base64.b64encode(audio_data).decode("utf-8")
        
        # Check the third call (playStream.stop)
        third_call_args = websocket.send_text.call_args_list[2][0][0]
        third_call_json = json.loads(third_call_args)
        assert third_call_json["type"] == "playStream.stop"
        assert third_call_json["streamId"] == stream_id 