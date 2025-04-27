"""
Pydantic models for OpenAI Realtime API message structures.

This module provides type-safe models for the messages exchanged with the OpenAI Realtime API,
including both incoming and outgoing message formats.
"""

from enum import Enum
from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, Field


class MessageRole(str, Enum):
    """Role of a participant in a conversation."""
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    FUNCTION = "function"


class OpenAIMessage(BaseModel):
    """Base model for OpenAI messages."""
    role: MessageRole
    content: str


class RealtimeBaseMessage(BaseModel):
    """Base model for Realtime API messages."""
    type: str


class RealtimeTranscriptMessage(RealtimeBaseMessage):
    """Transcription message from OpenAI Realtime API."""
    type: str = "transcript"
    text: str
    is_final: bool = Field(default=True)
    confidence: Optional[float] = None


class RealtimeTurnMessage(RealtimeBaseMessage):
    """Turn detection message from OpenAI Realtime API."""
    type: str = "turn"
    trigger: str  # 'vad', 'timeout', etc.


class RealtimeErrorMessage(RealtimeBaseMessage):
    """Error message from OpenAI Realtime API."""
    type: str = "error"
    code: str
    message: str
    details: Optional[Dict[str, Any]] = None


class RealtimeMessageContent(BaseModel):
    """Content part of a message within a conversation."""
    type: str = "text"
    text: str


class RealtimeMessage(BaseModel):
    """Message within a conversation."""
    role: MessageRole
    content: Union[str, List[RealtimeMessageContent]]
    name: Optional[str] = None


class RealtimeStreamMessage(RealtimeBaseMessage):
    """Stream message for chat responses from OpenAI Realtime API."""
    type: str = "message"
    message: RealtimeMessage


class RealtimeFunctionCall(BaseModel):
    """Function call structure in OpenAI Realtime API."""
    name: str
    arguments: str


class RealtimeFunctionMessage(RealtimeBaseMessage):
    """Function call message from OpenAI Realtime API."""
    type: str = "function_call"
    function_call: RealtimeFunctionCall


class RealtimeSessionResponse(BaseModel):
    """Response from session creation endpoint."""
    client_secret: Dict[str, str]
    expires_at: int
    id: str


class WebSocketErrorResponse(BaseModel):
    """Error response from OpenAI WebSocket connection."""
    error: Dict[str, Any] 