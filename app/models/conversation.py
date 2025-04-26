from typing import Dict, Any
from fastapi import WebSocket

class ConversationManager:
    """Manages active conversation states"""
    
    def __init__(self):
        self.active_conversations = {}
        
    def add_conversation(self, conversation_id: str, websocket: WebSocket, media_format: str):
        """Add a new conversation to the active conversations"""
        self.active_conversations[conversation_id] = {
            "websocket": websocket,
            "media_format": media_format,
        }
        
    def get_conversation(self, conversation_id: str) -> Dict[str, Any]:
        """Get an active conversation by ID"""
        return self.active_conversations.get(conversation_id)
        
    def remove_conversation(self, conversation_id: str):
        """Remove a conversation from active conversations"""
        if conversation_id in self.active_conversations:
            del self.active_conversations[conversation_id]
            
    def get_all_conversations(self) -> Dict[str, Dict[str, Any]]:
        """Get all active conversations"""
        return self.active_conversations 