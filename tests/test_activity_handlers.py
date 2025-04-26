import unittest
import json
from unittest.mock import AsyncMock, patch, MagicMock
import pytest

from app.handlers.activity_handlers import handle_activities, send_activities, hangup_call
from app.models.conversation import ConversationManager

@pytest.mark.asyncio
class TestActivityHandlers:
    
    async def test_handle_activities_start_event(self):
        # Setup
        websocket = AsyncMock()
        conversation_manager = MagicMock(spec=ConversationManager)
        message = {
            "conversationId": "test-conversation-id",
            "activities": [{"type": "event", "name": "start"}]
        }
        
        # Execute
        response = await handle_activities(message, websocket, conversation_manager)
        
        # Assert
        assert response is None
    
    async def test_handle_activities_dtmf_event(self):
        # Setup
        websocket = AsyncMock()
        conversation_manager = MagicMock(spec=ConversationManager)
        message = {
            "conversationId": "test-conversation-id",
            "activities": [{"type": "event", "name": "dtmf", "value": "5"}]
        }
        
        # Execute
        response = await handle_activities(message, websocket, conversation_manager)
        
        # Assert
        assert response is None
    
    async def test_handle_activities_hangup_event(self):
        # Setup
        websocket = AsyncMock()
        conversation_manager = MagicMock(spec=ConversationManager)
        message = {
            "conversationId": "test-conversation-id",
            "activities": [{"type": "event", "name": "hangup"}]
        }
        
        # Execute
        response = await handle_activities(message, websocket, conversation_manager)
        
        # Assert
        assert response is None
    
    async def test_handle_activities_unknown_event(self):
        # Setup
        websocket = AsyncMock()
        conversation_manager = MagicMock(spec=ConversationManager)
        message = {
            "conversationId": "test-conversation-id",
            "activities": [{"type": "event", "name": "unknown_event"}]
        }
        
        # Execute
        response = await handle_activities(message, websocket, conversation_manager)
        
        # Assert
        assert response is None
    
    async def test_send_activities(self):
        # Setup
        websocket = AsyncMock()
        activities = [{"type": "event", "name": "test_event"}]
        
        # Execute
        await send_activities(websocket, activities)
        
        # Assert
        expected_message = {"type": "activities", "activities": activities}
        websocket.send_text.assert_called_once_with(json.dumps(expected_message))
    
    async def test_hangup_call(self):
        # Setup
        websocket = AsyncMock()
        
        # Execute
        await hangup_call(websocket)
        
        # Assert
        expected_message = {"type": "activities", "activities": [{"type": "event", "name": "hangup"}]}
        websocket.send_text.assert_called_once_with(json.dumps(expected_message)) 