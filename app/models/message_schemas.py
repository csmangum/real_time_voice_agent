"""
Pydantic models for AudioCodes VoiceAI Connect Enterprise message schemas.

This module defines structured data models for all incoming and outgoing messages
in the AudioCodes Bot API WebSocket protocol, providing type validation and documentation.
"""

import base64
import re
from typing import Dict, List, Literal, Optional, Pattern, Union

from pydantic import BaseModel, Field, field_validator

# Regular expression patterns for validation
PHONE_PATTERN: Pattern = re.compile(r"^\+?[0-9\- ]{6,15}$")
UUID_PATTERN: Pattern = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
)
SUPPORTED_MEDIA_FORMATS = ["raw/lpcm16", "audio/wav", "audio/mp3", "audio/alaw"]


# Base Models
class BaseMessage(BaseModel):
    """Base model for all WebSocket messages."""

    type: str = Field(..., description="Message type identifier")
    conversationId: Optional[str] = Field(
        None, description="Unique conversation identifier"
    )

    @field_validator("conversationId")
    def validate_conversation_id(cls, v):
        """Validate that conversation ID is a UUID if provided."""
        if v is not None and not UUID_PATTERN.match(v):
            # Not enforcing UUID format as the service might use different formats
            # Just log a warning
            import logging

            from app.config.constants import LOGGER_NAME

            logger = logging.getLogger(LOGGER_NAME)
            logger.warning(f"Conversation ID does not match UUID pattern: {v}")
        return v


# Session Messages
class SessionInitiateMessage(BaseMessage):
    """Model for session.initiate message from AudioCodes."""

    type: Literal["session.initiate"]
    expectAudioMessages: bool = Field(
        ..., description="Whether the bot should send audio"
    )
    botName: str = Field(..., description="Configured name of the bot")
    caller: str = Field(..., description="Phone number of the caller")
    supportedMediaFormats: List[str] = Field(..., description="Supported audio formats")

    @field_validator("botName")
    def validate_bot_name(cls, v):
        """Validate that bot name is not empty."""
        if not v.strip():
            raise ValueError("Bot name cannot be empty")
        return v

    @field_validator("caller")
    def validate_caller(cls, v):
        """Validate that caller is a phone number if it looks like one."""
        if v.replace("+", "").replace("-", "").replace(" ", "").isdigit():
            if not PHONE_PATTERN.match(v):
                import logging

                from app.config.constants import LOGGER_NAME

                logger = logging.getLogger(LOGGER_NAME)
                logger.warning(f"Caller doesn't match expected phone pattern: {v}")
        return v

    @field_validator("supportedMediaFormats")
    def validate_media_formats(cls, v):
        """Validate that at least one supported media format is included."""
        if not v or not any(fmt in SUPPORTED_MEDIA_FORMATS for fmt in v):
            raise ValueError(
                f"At least one supported media format required: {SUPPORTED_MEDIA_FORMATS}"
            )
        return v


class SessionResumeMessage(BaseMessage):
    """Model for session.resume message from AudioCodes."""

    type: Literal["session.resume"]


class SessionEndMessage(BaseMessage):
    """Model for session.end message from AudioCodes."""

    type: Literal["session.end"]
    reasonCode: str = Field(..., description="Code indicating reason for session end")
    reason: str = Field(..., description="Description of why session ended")


class SessionAcceptedResponse(BaseMessage):
    """Model for session.accepted response to AudioCodes."""

    type: Literal["session.accepted"]
    mediaFormat: str = Field(..., description="Selected audio format for the session")

    @field_validator("mediaFormat")
    def validate_media_format(cls, v):
        """Validate that media format is supported."""
        if v not in SUPPORTED_MEDIA_FORMATS:
            raise ValueError(f"Unsupported media format: {v}")
        return v


class SessionErrorResponse(BaseMessage):
    """Model for session.error response to AudioCodes."""

    type: Literal["session.error"]
    reason: str = Field(..., description="Reason for rejecting the session")


# Stream Messages
class UserStreamStartMessage(BaseMessage):
    """Model for userStream.start message from AudioCodes."""

    type: Literal["userStream.start"]


class UserStreamChunkMessage(BaseMessage):
    """Model for userStream.chunk message from AudioCodes."""

    type: Literal["userStream.chunk"]
    audioChunk: str = Field(..., description="Base64-encoded audio data")

    @field_validator("audioChunk")
    def validate_audio_chunk(cls, v):
        """Validate that audio chunk is valid base64."""
        try:
            # Check if it's a valid base64 string
            if v:
                base64.b64decode(v)
            else:
                raise ValueError("Audio chunk cannot be empty")
        except Exception:
            raise ValueError("Invalid base64 encoded audio data")
        return v


class UserStreamStopMessage(BaseMessage):
    """Model for userStream.stop message from AudioCodes."""

    type: Literal["userStream.stop"]


class UserStreamStartedResponse(BaseMessage):
    """Model for userStream.started response to AudioCodes."""

    type: Literal["userStream.started"]


class UserStreamStoppedResponse(BaseMessage):
    """Model for userStream.stopped response to AudioCodes."""

    type: Literal["userStream.stopped"]


class UserStreamHypothesisResponse(BaseMessage):
    """Model for userStream.speech.hypothesis response to AudioCodes."""

    type: Literal["userStream.speech.hypothesis"]
    alternatives: List[Dict[str, str]] = Field(
        ..., description="List of recognition hypotheses"
    )

    @field_validator("alternatives")
    def validate_alternatives(cls, v):
        """Validate that alternatives contain text."""
        if not v:
            raise ValueError("At least one hypothesis required")
        for alt in v:
            if "text" not in alt:
                raise ValueError("Each hypothesis must contain 'text' field")
        return v


# Play Stream Messages
class PlayStreamStartMessage(BaseMessage):
    """Model for playStream.start message to AudioCodes."""

    type: Literal["playStream.start"]
    streamId: str = Field(..., description="Unique identifier for the stream")
    mediaFormat: str = Field(..., description="Audio format of the stream")

    @field_validator("mediaFormat")
    def validate_media_format(cls, v):
        """Validate that media format is supported."""
        if v not in SUPPORTED_MEDIA_FORMATS:
            raise ValueError(f"Unsupported media format: {v}")
        return v


class PlayStreamChunkMessage(BaseMessage):
    """Model for playStream.chunk message to AudioCodes."""

    type: Literal["playStream.chunk"]
    streamId: str = Field(..., description="Stream identifier")
    audioChunk: str = Field(..., description="Base64-encoded audio data")

    @field_validator("audioChunk")
    def validate_audio_chunk(cls, v):
        """Validate that audio chunk is valid base64."""
        try:
            # Check if it's a valid base64 string
            if v:
                base64.b64decode(v)
            else:
                raise ValueError("Audio chunk cannot be empty")
        except Exception:
            raise ValueError("Invalid base64 encoded audio data")
        return v


class PlayStreamStopMessage(BaseMessage):
    """Model for playStream.stop message to AudioCodes."""

    type: Literal["playStream.stop"]
    streamId: str = Field(..., description="Stream identifier")


# Activity Messages
class ActivityEvent(BaseModel):
    """Model for activity event."""

    type: Literal["event"]
    name: str = Field(..., description="Event name (start, dtmf, hangup)")
    value: Optional[str] = Field(None, description="Event value, e.g., DTMF digit")

    @field_validator("name")
    def validate_name(cls, v):
        """Validate that event name is a known type."""
        if v not in ["start", "dtmf", "hangup"]:
            import logging

            from app.config.constants import LOGGER_NAME

            logger = logging.getLogger(LOGGER_NAME)
            logger.warning(f"Unknown event name: {v}")
        return v

    @field_validator("value")
    def validate_value(cls, v, values):
        """Validate that value is appropriate for the event type."""
        if values.data.get("name") == "dtmf" and v is not None:
            if not v in "0123456789*#ABCD":
                raise ValueError(f"Invalid DTMF value: {v}")
        return v


class ActivitiesMessage(BaseMessage):
    """Model for activities message from AudioCodes."""

    type: Literal["activities"]
    activities: List[ActivityEvent] = Field(..., description="List of activity events")

    @field_validator("activities")
    def validate_activities(cls, v):
        """Validate that there is at least one activity."""
        if not v:
            raise ValueError("At least one activity required")
        return v


# Connection Messages
class ConnectionValidateMessage(BaseMessage):
    """Model for connection.validate message from AudioCodes."""

    type: Literal["connection.validate"]


class ConnectionValidatedResponse(BaseMessage):
    """Model for connection.validated response to AudioCodes."""

    type: Literal["connection.validated"]
    success: bool = Field(..., description="Whether validation was successful")


# Union type for all possible incoming messages
IncomingMessage = Union[
    SessionInitiateMessage,
    SessionResumeMessage,
    SessionEndMessage,
    UserStreamStartMessage,
    UserStreamChunkMessage,
    UserStreamStopMessage,
    ActivitiesMessage,
    ConnectionValidateMessage,
]

# Union type for all possible outgoing messages
OutgoingMessage = Union[
    SessionAcceptedResponse,
    SessionErrorResponse,
    UserStreamStartedResponse,
    UserStreamStoppedResponse,
    UserStreamHypothesisResponse,
    PlayStreamStartMessage,
    PlayStreamChunkMessage,
    PlayStreamStopMessage,
    ActivitiesMessage,
    ConnectionValidatedResponse,
]
