import unittest
import json
from unittest.mock import AsyncMock, patch, MagicMock
import pytest

from app.handlers.activity_handlers import handle_activities, send_activities, hangup_call
from app.models.conversation import ConversationManager
from app.models.message_schemas import ActivityEvent, ActivitiesMessage
from pydantic import ValidationError

@pytest.mark.asyncio
class TestActivityHandlers:
    
    async def test_handle_activities_start_event(self):
        # Setup
        websocket = AsyncMock()
        conversation_manager = MagicMock(spec=ConversationManager)
        message = ActivitiesMessage(
            type="activities",
            conversationId="test-conversation-id",
            activities=[ActivityEvent(type="event", name="start")]
        )
        
        # Execute
        response = await handle_activities(message.model_dump(), websocket, conversation_manager)
        
        # Assert
        assert response is None
    
    async def test_handle_activities_dtmf_event(self):
        # Setup
        websocket = AsyncMock()
        conversation_manager = MagicMock(spec=ConversationManager)
        message = ActivitiesMessage(
            type="activities",
            conversationId="test-conversation-id",
            activities=[ActivityEvent(type="event", name="dtmf", value="5")]
        )
        
        # Execute
        response = await handle_activities(message.model_dump(), websocket, conversation_manager)
        
        # Assert
        assert response is None
    
    async def test_handle_activities_hangup_event(self):
        # Setup
        websocket = AsyncMock()
        conversation_manager = MagicMock(spec=ConversationManager)
        message = ActivitiesMessage(
            type="activities",
            conversationId="test-conversation-id",
            activities=[ActivityEvent(type="event", name="hangup")]
        )
        
        # Execute
        response = await handle_activities(message.model_dump(), websocket, conversation_manager)
        
        # Assert
        assert response is None
    
    async def test_handle_activities_unknown_event(self):
        # Setup
        websocket = AsyncMock()
        conversation_manager = MagicMock(spec=ConversationManager)
        # Testing with an unknown event - we'll still use the model but it will log a warning
        message = ActivitiesMessage(
            type="activities",
            conversationId="test-conversation-id",
            activities=[ActivityEvent(type="event", name="unknown_event")]
        )
        
        # Execute
        response = await handle_activities(message.model_dump(), websocket, conversation_manager)
        
        # Assert
        assert response is None
    
    async def test_handle_activities_validation_error(self):
        # Setup
        websocket = AsyncMock()
        conversation_manager = MagicMock(spec=ConversationManager)
        # Invalid message structure
        message = {
            "type": "activities",
            "conversationId": "test-conversation-id",
            # Missing activities list
        }
        
        # Execute
        response = await handle_activities(message, websocket, conversation_manager)
        
        # Assert
        assert response is None
    
    async def test_send_activities(self):
        # Setup
        websocket = AsyncMock()
        activities = [ActivityEvent(type="event", name="test_event")]
        
        # Execute
        await send_activities(websocket, activities)
        
        # Assert
        expected_message = ActivitiesMessage(
            type="activities", 
            activities=activities
        )
        websocket.send_text.assert_called_once_with(expected_message.json())
    
    async def test_hangup_call(self):
        # Setup
        websocket = AsyncMock()
        
        # Execute
        await hangup_call(websocket)
        
        # Assert
        expected_message = ActivitiesMessage(
            type="activities", 
            activities=[ActivityEvent(type="event", name="hangup")]
        )
        websocket.send_text.assert_called_once_with(expected_message.json()) 