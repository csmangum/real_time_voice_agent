import base64
import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.handlers.stream_handlers import (
    handle_user_stream_chunk,
    handle_user_stream_start,
    handle_user_stream_stop,
    send_play_stream,
)
from app.models.conversation import ConversationManager
from app.models.message_schemas import (
    PlayStreamChunkMessage,
    PlayStreamStartMessage,
    PlayStreamStopMessage,
    UserStreamChunkMessage,
    UserStreamStartedResponse,
    UserStreamStartMessage,
    UserStreamStopMessage,
    UserStreamStoppedResponse,
)


@pytest.mark.asyncio
class TestStreamHandlers:

    async def test_handle_user_stream_start(self):
        # Setup
        websocket = AsyncMock()
        conversation_manager = MagicMock(spec=ConversationManager)
        message = UserStreamStartMessage(
            type="userStream.start", conversationId="test-conversation-id"
        )

        # Execute
        response = await handle_user_stream_start(
            message.model_dump(), websocket, conversation_manager
        )

        # Assert
        expected_response = UserStreamStartedResponse(
            type="userStream.started", conversationId="test-conversation-id"
        )
        assert response.model_dump() == expected_response.model_dump()

    async def test_handle_user_stream_start_validation_error(self):
        # Setup
        websocket = AsyncMock()
        conversation_manager = MagicMock(spec=ConversationManager)
        # Missing required type field
        message = {"conversationId": "test-conversation-id"}

        # Execute
        response = await handle_user_stream_start(
            message, websocket, conversation_manager
        )

        # Assert
        # The handler returns a basic response even for validation errors
        expected_response = UserStreamStartedResponse(
            type="userStream.started", conversationId=None
        )
        assert response.model_dump() == expected_response.model_dump()

    async def test_handle_user_stream_chunk(self):
        # Setup
        websocket = AsyncMock()
        conversation_manager = MagicMock(spec=ConversationManager)
        # Base64 encoded sample audio chunk
        audio_chunk = base64.b64encode(b"test_audio_data").decode("utf-8")
        message = UserStreamChunkMessage(
            type="userStream.chunk",
            conversationId="test-conversation-id",
            audioChunk=audio_chunk,
        )

        # Execute
        response = await handle_user_stream_chunk(
            message.model_dump(), websocket, conversation_manager
        )

        # Assert
        assert response is None

    async def test_handle_user_stream_chunk_validation_error(self):
        # Setup
        websocket = AsyncMock()
        conversation_manager = MagicMock(spec=ConversationManager)
        # Missing required audioChunk field
        message = {"type": "userStream.chunk", "conversationId": "test-conversation-id"}

        # Execute
        response = await handle_user_stream_chunk(
            message, websocket, conversation_manager
        )

        # Assert
        assert response is None

    async def test_handle_user_stream_stop(self):
        # Setup
        websocket = AsyncMock()
        conversation_manager = MagicMock(spec=ConversationManager)
        message = UserStreamStopMessage(
            type="userStream.stop", conversationId="test-conversation-id"
        )

        # Execute
        response = await handle_user_stream_stop(
            message.model_dump(), websocket, conversation_manager
        )

        # Assert
        expected_response = UserStreamStoppedResponse(
            type="userStream.stopped", conversationId="test-conversation-id"
        )
        assert response.model_dump() == expected_response.model_dump()

    async def test_handle_user_stream_stop_validation_error(self):
        # Setup
        websocket = AsyncMock()
        conversation_manager = MagicMock(spec=ConversationManager)
        # Missing required type field
        message = {"conversationId": "test-conversation-id"}

        # Execute
        response = await handle_user_stream_stop(
            message, websocket, conversation_manager
        )

        # Assert
        # The handler returns a basic response even for validation errors
        expected_response = UserStreamStoppedResponse(
            type="userStream.stopped", conversationId=None
        )
        assert response.model_dump() == expected_response.model_dump()

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

        # Expected models for each message
        start_message = PlayStreamStartMessage(
            type="playStream.start", streamId=stream_id, mediaFormat=media_format
        )

        chunk_message = PlayStreamChunkMessage(
            type="playStream.chunk",
            streamId=stream_id,
            audioChunk=base64.b64encode(audio_data).decode("utf-8"),
        )

        stop_message = PlayStreamStopMessage(type="playStream.stop", streamId=stream_id)

        # Check the first call (playStream.start)
        first_call_args = websocket.send_text.call_args_list[0][0][0]
        # We're expecting start_message.json() was sent
        assert json.loads(first_call_args) == json.loads(start_message.json())

        # Check the second call (playStream.chunk)
        second_call_args = websocket.send_text.call_args_list[1][0][0]
        assert json.loads(second_call_args) == json.loads(chunk_message.json())

        # Check the third call (playStream.stop)
        third_call_args = websocket.send_text.call_args_list[2][0][0]
        assert json.loads(third_call_args) == json.loads(stop_message.json())
