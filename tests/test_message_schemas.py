"""
Unit tests for the message schemas.

These tests validate that the Pydantic models correctly validate message data
and that the validation rules work as expected.
"""

import base64
import pytest
from pydantic import ValidationError

from app.models.message_schemas import (
    ActivitiesMessage,
    ActivityEvent,
    BaseMessage,
    ConnectionValidateMessage,
    ConnectionValidatedResponse,
    PlayStreamChunkMessage,
    PlayStreamStartMessage,
    PlayStreamStopMessage,
    SessionAcceptedResponse,
    SessionEndMessage,
    SessionErrorResponse,
    SessionInitiateMessage,
    SessionResumeMessage,
    UserStreamChunkMessage,
    UserStreamHypothesisResponse,
    UserStreamStartMessage,
    UserStreamStartedResponse,
    UserStreamStopMessage,
    UserStreamStoppedResponse,
)


class TestBaseMessage:
    """Tests for the BaseMessage class."""

    def test_valid_base_message(self):
        """Test that a valid base message can be created."""
        message = BaseMessage(type="test.message")
        assert message.type == "test.message"
        assert message.conversationId is None

    def test_valid_base_message_with_conversation_id(self):
        """Test that a base message with a conversation ID can be created."""
        message = BaseMessage(
            type="test.message", conversationId="550e8400-e29b-41d4-a716-446655440000"
        )
        assert message.type == "test.message"
        assert message.conversationId == "550e8400-e29b-41d4-a716-446655440000"

    def test_missing_type(self):
        """Test that a message without a type raises a validation error."""
        with pytest.raises(ValidationError):
            BaseMessage()


class TestSessionMessages:
    """Tests for session-related message models."""

    def test_valid_session_initiate(self):
        """Test that a valid session.initiate message can be created."""
        message = SessionInitiateMessage(
            type="session.initiate",
            expectAudioMessages=True,
            botName="TestBot",
            caller="+12345678901",
            supportedMediaFormats=["raw/lpcm16", "audio/wav"],
        )
        assert message.type == "session.initiate"
        assert message.expectAudioMessages is True
        assert message.botName == "TestBot"
        assert message.caller == "+12345678901"
        assert "raw/lpcm16" in message.supportedMediaFormats

    def test_invalid_session_initiate_no_formats(self):
        """Test that a session.initiate without supported formats raises an error."""
        with pytest.raises(ValidationError):
            SessionInitiateMessage(
                type="session.initiate",
                expectAudioMessages=True,
                botName="TestBot",
                caller="+12345678901",
                supportedMediaFormats=[],
            )

    def test_invalid_session_initiate_unsupported_format(self):
        """Test that a session.initiate with only unsupported formats raises an error."""
        with pytest.raises(ValidationError):
            SessionInitiateMessage(
                type="session.initiate",
                expectAudioMessages=True,
                botName="TestBot",
                caller="+12345678901",
                supportedMediaFormats=["invalid/format"],
            )

    def test_valid_session_accepted(self):
        """Test that a valid session.accepted response can be created."""
        response = SessionAcceptedResponse(
            type="session.accepted", mediaFormat="raw/lpcm16"
        )
        assert response.type == "session.accepted"
        assert response.mediaFormat == "raw/lpcm16"

    def test_invalid_session_accepted_format(self):
        """Test that a session.accepted with invalid format raises an error."""
        with pytest.raises(ValidationError):
            SessionAcceptedResponse(
                type="session.accepted", mediaFormat="invalid/format"
            )


class TestStreamMessages:
    """Tests for stream-related message models."""

    def test_valid_user_stream_chunk(self):
        """Test that a valid userStream.chunk message can be created."""
        # Create a simple base64 string
        audio_data = base64.b64encode(b"test audio data").decode("utf-8")
        message = UserStreamChunkMessage(
            type="userStream.chunk", audioChunk=audio_data
        )
        assert message.type == "userStream.chunk"
        assert message.audioChunk == audio_data

    def test_invalid_user_stream_chunk_empty(self):
        """Test that a userStream.chunk with empty audio raises an error."""
        with pytest.raises(ValidationError):
            UserStreamChunkMessage(type="userStream.chunk", audioChunk="")

    def test_invalid_user_stream_chunk_not_base64(self):
        """Test that a userStream.chunk with invalid base64 raises an error."""
        with pytest.raises(ValidationError):
            UserStreamChunkMessage(type="userStream.chunk", audioChunk="not base64!")

    def test_valid_play_stream_start(self):
        """Test that a valid playStream.start message can be created."""
        message = PlayStreamStartMessage(
            type="playStream.start", streamId="stream1", mediaFormat="raw/lpcm16"
        )
        assert message.type == "playStream.start"
        assert message.streamId == "stream1"
        assert message.mediaFormat == "raw/lpcm16"

    def test_invalid_play_stream_start_format(self):
        """Test that a playStream.start with invalid format raises an error."""
        with pytest.raises(ValidationError):
            PlayStreamStartMessage(
                type="playStream.start",
                streamId="stream1",
                mediaFormat="invalid/format",
            )


class TestActivityMessages:
    """Tests for activity-related message models."""

    def test_valid_activity_event(self):
        """Test that a valid activity event can be created."""
        event = ActivityEvent(type="event", name="dtmf", value="5")
        assert event.type == "event"
        assert event.name == "dtmf"
        assert event.value == "5"

    def test_valid_hangup_activity(self):
        """Test that a valid hangup activity can be created."""
        event = ActivityEvent(type="event", name="hangup")
        assert event.type == "event"
        assert event.name == "hangup"
        assert event.value is None

    def test_invalid_dtmf_value(self):
        """Test that a dtmf activity with invalid value raises an error."""
        with pytest.raises(ValidationError):
            ActivityEvent(type="event", name="dtmf", value="Z")

    def test_valid_activities_message(self):
        """Test that a valid activities message can be created."""
        events = [
            ActivityEvent(type="event", name="dtmf", value="1"),
            ActivityEvent(type="event", name="hangup"),
        ]
        message = ActivitiesMessage(
            type="activities", activities=events, conversationId="session123"
        )
        assert message.type == "activities"
        assert len(message.activities) == 2
        assert message.activities[0].name == "dtmf"
        assert message.activities[1].name == "hangup"

    def test_invalid_empty_activities(self):
        """Test that an activities message with no activities raises an error."""
        with pytest.raises(ValidationError):
            ActivitiesMessage(type="activities", activities=[])


class TestHypothesisMessages:
    """Tests for hypothesis-related message models."""

    def test_valid_hypothesis(self):
        """Test that a valid hypothesis message can be created."""
        message = UserStreamHypothesisResponse(
            type="userStream.speech.hypothesis",
            alternatives=[{"text": "hello world"}, {"text": "hello word"}],
        )
        assert message.type == "userStream.speech.hypothesis"
        assert len(message.alternatives) == 2
        assert message.alternatives[0]["text"] == "hello world"

    def test_invalid_empty_alternatives(self):
        """Test that a hypothesis with no alternatives raises an error."""
        with pytest.raises(ValidationError):
            UserStreamHypothesisResponse(
                type="userStream.speech.hypothesis", alternatives=[]
            )

    def test_invalid_missing_text(self):
        """Test that a hypothesis with alternative missing text raises an error."""
        with pytest.raises(ValidationError):
            UserStreamHypothesisResponse(
                type="userStream.speech.hypothesis",
                alternatives=[{"confidence": 0.9}],
            ) 