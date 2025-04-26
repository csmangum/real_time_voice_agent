from unittest.mock import AsyncMock, patch, MagicMock
import pytest

from app.handlers.session_handlers import (
    handle_session_initiate,
    handle_session_resume,
    handle_session_end,
    handle_connection_validate
)
from app.models.conversation import ConversationManager
from app.models.message_schemas import (
    SessionInitiateMessage,
    SessionResumeMessage,
    SessionEndMessage,
    ConnectionValidateMessage,
    SessionAcceptedResponse,
    SessionErrorResponse,
    ConnectionValidatedResponse
)
from pydantic import ValidationError

@pytest.mark.asyncio
class TestSessionHandlers:
    
    async def test_handle_session_initiate_supported_format(self):
        # Setup
        websocket = AsyncMock()
        conversation_manager = MagicMock(spec=ConversationManager)
        message = SessionInitiateMessage(
            type="session.initiate",
            conversationId="test-conversation-id",
            expectAudioMessages=True,
            botName="TestBot",
            caller="+12345678901",
            supportedMediaFormats=["raw/lpcm16", "other/format"]
        )
        
        # Execute
        response = await handle_session_initiate(message.model_dump(), websocket, conversation_manager)
        
        # Assert
        expected_response = SessionAcceptedResponse(
            type="session.accepted", 
            mediaFormat="raw/lpcm16",
            conversationId="test-conversation-id"
        )
        assert response.model_dump() == expected_response.model_dump()
        
        # Check that the conversation was added to the manager
        conversation_manager.add_conversation.assert_called_once_with(
            "test-conversation-id", websocket, "raw/lpcm16"
        )
        
        # Check that the accepted response was sent to the websocket
        websocket.send_text.assert_called_once_with(expected_response.json())
    
    async def test_handle_session_initiate_unsupported_format(self):
        # Setup
        websocket = AsyncMock()
        conversation_manager = MagicMock(spec=ConversationManager)
        # Create a valid message with only unsupported formats
        # Include at least one valid format to pass validation, but make it a format
        # that doesn't match the one we're looking for (raw/lpcm16)
        message = SessionInitiateMessage(
            type="session.initiate",
            conversationId="test-conversation-id",
            expectAudioMessages=True,
            botName="TestBot",
            caller="+12345678901",
            supportedMediaFormats=["audio/mp3"]  # Valid format but not raw/lpcm16
        )
        
        # Execute
        response = await handle_session_initiate(message.model_dump(), websocket, conversation_manager)
        
        # Assert
        expected_response = SessionErrorResponse(
            type="session.error",
            reason="Required media format not supported",
            conversationId="test-conversation-id"
        )
        assert response.model_dump() == expected_response.model_dump()
        
        # Check that the conversation was not added to the manager
        conversation_manager.add_conversation.assert_not_called()
        
        # Check that the error response was sent to the websocket
        websocket.send_text.assert_called_once_with(expected_response.json())
    
    async def test_handle_session_initiate_validation_error(self):
        # Setup
        websocket = AsyncMock()
        conversation_manager = MagicMock(spec=ConversationManager)
        # Missing required fields
        message = {"type": "session.initiate"}
        
        # Execute
        response = await handle_session_initiate(message, websocket, conversation_manager)
        
        # Assert
        expected_response = SessionErrorResponse(
            type="session.error",
            reason="Invalid message format"
        )
        assert response.model_dump()["type"] == expected_response.model_dump()["type"]
        assert response.model_dump()["reason"] == expected_response.model_dump()["reason"]
        
        # Check that the error response was sent to the websocket
        websocket.send_text.assert_called_once()
    
    async def test_handle_session_resume(self):
        # Setup
        websocket = AsyncMock()
        conversation_manager = MagicMock(spec=ConversationManager)
        message = SessionResumeMessage(
            type="session.resume",
            conversationId="test-conversation-id"
        )
        
        # Execute
        response = await handle_session_resume(message.model_dump(), websocket, conversation_manager)
        
        # Assert
        expected_response = SessionAcceptedResponse(
            type="session.accepted", 
            mediaFormat="raw/lpcm16",
            conversationId="test-conversation-id"
        )
        assert response.model_dump() == expected_response.model_dump()
    
    async def test_handle_session_resume_validation_error(self):
        # Setup
        websocket = AsyncMock()
        conversation_manager = MagicMock(spec=ConversationManager)
        # Missing required type field
        message = {"conversationId": "test-conversation-id"}
        
        # Execute
        response = await handle_session_resume(message, websocket, conversation_manager)
        
        # Assert
        expected_response = SessionErrorResponse(
            type="session.error",
            reason="Invalid message format"
        )
        assert response.model_dump()["type"] == expected_response.model_dump()["type"]
        assert response.model_dump()["reason"] == expected_response.model_dump()["reason"]
    
    async def test_handle_session_end(self):
        # Setup
        websocket = AsyncMock()
        conversation_manager = MagicMock(spec=ConversationManager)
        message = SessionEndMessage(
            type="session.end",
            conversationId="test-conversation-id",
            reasonCode="normal",
            reason="User ended the session"
        )
        
        # Execute
        response = await handle_session_end(message.model_dump(), websocket, conversation_manager)
        
        # Assert
        assert response is None
        
        # Check that the conversation was removed from the manager
        conversation_manager.remove_conversation.assert_called_once_with("test-conversation-id")
    
    async def test_handle_session_end_validation_error(self):
        # Setup
        websocket = AsyncMock()
        conversation_manager = MagicMock(spec=ConversationManager)
        # Missing required fields
        message = {"type": "session.end"}
        
        # Execute
        response = await handle_session_end(message, websocket, conversation_manager)
        
        # Assert
        assert response is None
    
    async def test_handle_connection_validate(self):
        # Setup
        websocket = AsyncMock()
        conversation_manager = MagicMock(spec=ConversationManager)
        message = ConnectionValidateMessage(
            type="connection.validate"
        )
        
        # Execute
        response = await handle_connection_validate(message.model_dump(), websocket, conversation_manager)
        
        # Assert
        expected_response = ConnectionValidatedResponse(
            type="connection.validated", 
            success=True
        )
        assert response.model_dump() == expected_response.model_dump()
    
    async def test_handle_connection_validate_validation_error(self):
        # Setup
        websocket = AsyncMock()
        conversation_manager = MagicMock(spec=ConversationManager)
        # Missing required type field
        message = {}
        
        # Execute
        response = await handle_connection_validate(message, websocket, conversation_manager)
        
        # Assert
        expected_response = ConnectionValidatedResponse(
            type="connection.validated", 
            success=True
        )
        assert response.model_dump() == expected_response.model_dump() 