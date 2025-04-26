import unittest
import json
from unittest.mock import AsyncMock, patch, MagicMock
import pytest

from app.handlers.session_handlers import (
    handle_session_initiate,
    handle_session_resume,
    handle_session_end,
    handle_connection_validate
)
from app.models.conversation import ConversationManager

@pytest.mark.asyncio
class TestSessionHandlers:
    
    async def test_handle_session_initiate_supported_format(self):
        # Setup
        websocket = AsyncMock()
        conversation_manager = MagicMock(spec=ConversationManager)
        message = {
            "conversationId": "test-conversation-id",
            "supportedMediaFormats": ["raw/lpcm16", "other/format"]
        }
        
        # Execute
        response = await handle_session_initiate(message, websocket, conversation_manager)
        
        # Assert
        expected_response = {"type": "session.accepted", "mediaFormat": "raw/lpcm16"}
        assert response == expected_response
        
        # Check that the conversation was added to the manager
        conversation_manager.add_conversation.assert_called_once_with(
            "test-conversation-id", websocket, "raw/lpcm16"
        )
        
        # Check that the accepted response was sent to the websocket
        websocket.send_text.assert_called_once_with(json.dumps(expected_response))
    
    async def test_handle_session_initiate_unsupported_format(self):
        # Setup
        websocket = AsyncMock()
        conversation_manager = MagicMock(spec=ConversationManager)
        message = {
            "conversationId": "test-conversation-id",
            "supportedMediaFormats": ["unsupported/format"]
        }
        
        # Execute
        response = await handle_session_initiate(message, websocket, conversation_manager)
        
        # Assert
        expected_response = {
            "type": "session.error",
            "reason": "Required media format not supported"
        }
        assert response == expected_response
        
        # Check that the conversation was not added to the manager
        conversation_manager.add_conversation.assert_not_called()
        
        # Check that the error response was sent to the websocket
        websocket.send_text.assert_called_once_with(json.dumps(expected_response))
    
    async def test_handle_session_resume(self):
        # Setup
        websocket = AsyncMock()
        conversation_manager = MagicMock(spec=ConversationManager)
        message = {"conversationId": "test-conversation-id"}
        
        # Execute
        response = await handle_session_resume(message, websocket, conversation_manager)
        
        # Assert
        expected_response = {"type": "session.accepted", "mediaFormat": "raw/lpcm16"}
        assert response == expected_response
    
    async def test_handle_session_end(self):
        # Setup
        websocket = AsyncMock()
        conversation_manager = MagicMock(spec=ConversationManager)
        message = {
            "conversationId": "test-conversation-id",
            "reasonCode": "normal",
            "reason": "User ended the session"
        }
        
        # Execute
        response = await handle_session_end(message, websocket, conversation_manager)
        
        # Assert
        assert response is None
        
        # Check that the conversation was removed from the manager
        conversation_manager.remove_conversation.assert_called_once_with("test-conversation-id")
    
    async def test_handle_connection_validate(self):
        # Setup
        websocket = AsyncMock()
        conversation_manager = MagicMock(spec=ConversationManager)
        message = {}
        
        # Execute
        response = await handle_connection_validate(message, websocket, conversation_manager)
        
        # Assert
        expected_response = {"type": "connection.validated", "success": True}
        assert response == expected_response 