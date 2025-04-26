import unittest
from unittest.mock import AsyncMock, MagicMock

from app.models.conversation import ConversationManager

class TestConversationManager(unittest.TestCase):
    
    def setUp(self):
        self.conversation_manager = ConversationManager()
        self.websocket = AsyncMock()
        self.conversation_id = "test-conversation-id"
        self.media_format = "raw/lpcm16"
        
    def test_add_conversation(self):
        # Execute
        self.conversation_manager.add_conversation(
            self.conversation_id, self.websocket, self.media_format
        )
        
        # Assert
        self.assertIn(self.conversation_id, self.conversation_manager.active_conversations)
        self.assertEqual(
            self.conversation_manager.active_conversations[self.conversation_id]["websocket"],
            self.websocket
        )
        self.assertEqual(
            self.conversation_manager.active_conversations[self.conversation_id]["media_format"],
            self.media_format
        )
        
    def test_get_conversation(self):
        # Setup
        self.conversation_manager.add_conversation(
            self.conversation_id, self.websocket, self.media_format
        )
        
        # Execute
        conversation = self.conversation_manager.get_conversation(self.conversation_id)
        
        # Assert
        self.assertEqual(conversation["websocket"], self.websocket)
        self.assertEqual(conversation["media_format"], self.media_format)
        
    def test_get_nonexistent_conversation(self):
        # Execute
        conversation = self.conversation_manager.get_conversation("nonexistent-id")
        
        # Assert
        self.assertIsNone(conversation)
        
    def test_remove_conversation(self):
        # Setup
        self.conversation_manager.add_conversation(
            self.conversation_id, self.websocket, self.media_format
        )
        
        # Execute
        self.conversation_manager.remove_conversation(self.conversation_id)
        
        # Assert
        self.assertNotIn(self.conversation_id, self.conversation_manager.active_conversations)
        
    def test_remove_nonexistent_conversation(self):
        # Execute - should not raise an exception
        self.conversation_manager.remove_conversation("nonexistent-id")
        
    def test_get_all_conversations(self):
        # Setup
        conversation_id1 = "conversation-1"
        conversation_id2 = "conversation-2"
        websocket1 = AsyncMock()
        websocket2 = AsyncMock()
        
        self.conversation_manager.add_conversation(
            conversation_id1, websocket1, self.media_format
        )
        self.conversation_manager.add_conversation(
            conversation_id2, websocket2, self.media_format
        )
        
        # Execute
        all_conversations = self.conversation_manager.get_all_conversations()
        
        # Assert
        self.assertEqual(len(all_conversations), 2)
        self.assertIn(conversation_id1, all_conversations)
        self.assertIn(conversation_id2, all_conversations)
        self.assertEqual(all_conversations[conversation_id1]["websocket"], websocket1)
        self.assertEqual(all_conversations[conversation_id2]["websocket"], websocket2) 