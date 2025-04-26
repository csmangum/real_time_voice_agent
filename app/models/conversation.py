"""
Conversation state management module for AudioCodes VoiceAI Connect integration.

This module provides the ConversationManager class which tracks active WebSocket
connections and their associated media formats during voice interactions with
the AudioCodes VoiceAI Connect Enterprise platform. The manager handles conversation
lifecycle including tracking, retrieving, and removing conversation state.
"""

from typing import Any, Dict

from fastapi import WebSocket


class ConversationManager:
    """
    Manages active conversation states for AudioCodes VoiceAI Connect connections.

    This class maintains a registry of active voice call conversations, associating
    each conversation ID with its WebSocket connection and media format preferences.
    It provides methods to add, retrieve, and remove conversations during the call
    lifecycle.
    """

    def __init__(self):
        """Initialize an empty dictionary of active conversations."""
        self.active_conversations = {}

    def add_conversation(
        self, conversation_id: str, websocket: WebSocket, media_format: str
    ):
        """
        Add a new conversation to the active conversations registry.

        Args:
            conversation_id: Unique identifier for the conversation from AudioCodes
            websocket: The active WebSocket connection for the conversation
            media_format: Audio format used for the conversation (e.g., 'raw/lpcm16')
        """
        self.active_conversations[conversation_id] = {
            "websocket": websocket,
            "media_format": media_format,
        }

    def get_conversation(self, conversation_id: str) -> Dict[str, Any]:
        """
        Get an active conversation by its ID.

        Args:
            conversation_id: Unique identifier for the conversation

        Returns:
            Dictionary containing conversation data including websocket and media_format,
            or None if the conversation does not exist
        """
        return self.active_conversations.get(conversation_id)

    def remove_conversation(self, conversation_id: str):
        """
        Remove a conversation from active conversations registry.

        Args:
            conversation_id: Unique identifier for the conversation to remove
        """
        if conversation_id in self.active_conversations:
            del self.active_conversations[conversation_id]

    def get_all_conversations(self) -> Dict[str, Dict[str, Any]]:
        """
        Get all active conversations.

        Returns:
            Dictionary mapping conversation IDs to their respective conversation data
        """
        return self.active_conversations
