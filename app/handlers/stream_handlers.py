"""
Handles audio streaming between the bot and AudioCodes VoiceAI Connect Enterprise.

This module processes audio stream control messages (start, chunk, stop) from AudioCodes
and provides functions to stream audio back to the user. It implements the audio streaming
protocol defined in the AudioCodes Bot API WebSocket mode.
"""

import base64
import logging
from typing import Any, Dict, Optional

from fastapi import WebSocket
from pydantic import ValidationError

from app.config.constants import LOGGER_NAME
from app.models.conversation import ConversationManager
from app.models.message_schemas import (
    PlayStreamChunkMessage,
    PlayStreamStartMessage,
    PlayStreamStopMessage,
    UserStreamChunkMessage,
    UserStreamStartedResponse,
    UserStreamStartMessage,
    UserStreamStopMessage,
    UserStreamStoppedResponse,
)

logger = logging.getLogger(LOGGER_NAME)


async def handle_user_stream_start(
    message: Dict[str, Any],
    websocket: WebSocket,
    conversation_manager: ConversationManager,
) -> UserStreamStartedResponse:
    """
    Handle the userStream.start message from AudioCodes VoiceAI Connect Enterprise.

    This message indicates a request to start audio streaming to the bot.
    The bot should respond with a userStream.started message to indicate readiness
    to receive audio chunks.

    Args:
        message: The userStream.start message
        websocket: The WebSocket connection to respond through
        conversation_manager: Manager for tracking active conversations

    Returns:
        A userStream.started response message
    """
    try:
        # Validate incoming message
        stream_start = UserStreamStartMessage(**message)
        conversation_id = stream_start.conversationId

        # Signal that the bot is ready to receive audio chunks
        logger.info(f"User stream starting for conversation: {conversation_id}")

        # Create response
        return UserStreamStartedResponse(
            type="userStream.started", conversationId=conversation_id
        )

    except ValidationError as e:
        logger.error(f"Invalid userStream.start message: {e}")
        # Return a basic response even if validation fails
        return UserStreamStartedResponse(type="userStream.started")


async def handle_user_stream_chunk(
    message: Dict[str, Any],
    websocket: WebSocket,
    conversation_manager: ConversationManager,
) -> None:
    """
    Handle the userStream.chunk message from AudioCodes VoiceAI Connect Enterprise.

    This message contains streamed audio data from the user.
    In a full implementation, this would process the audio with speech recognition.

    Args:
        message: The userStream.chunk message containing the audioChunk in base64 encoding
        websocket: The WebSocket connection to send responses through
        conversation_manager: Manager for tracking active conversations

    Returns:
        None, though a real implementation might send hypothesis messages
    """
    try:
        # Validate incoming message
        stream_chunk = UserStreamChunkMessage(**message)

        # Process the audio chunk (in a real implementation, this would handle speech recognition)
        # Extract the audio data
        audio_chunk = stream_chunk.audioChunk
        conversation_id = stream_chunk.conversationId

        # Here you would process the audio data, e.g., with a speech recognition engine
        # For demonstration, we'll just log that we received a chunk
        logger.debug(f"Processing audio chunk of length: {len(audio_chunk)}")

        # In a real implementation, you might want to send hypothesis messages during recognition
        # Example:
        # hypothesis_response = UserStreamHypothesisResponse(
        #     type="userStream.speech.hypothesis",
        #     alternatives=[{"text": "Partial recognition text"}],
        #     conversationId=conversation_id
        # )
        # await websocket.send_text(hypothesis_response.json())

    except ValidationError as e:
        logger.error(f"Invalid userStream.chunk message: {e}")

    return None


async def handle_user_stream_stop(
    message: Dict[str, Any],
    websocket: WebSocket,
    conversation_manager: ConversationManager,
) -> UserStreamStoppedResponse:
    """
    Handle the userStream.stop message from AudioCodes VoiceAI Connect Enterprise.

    This message indicates the end of audio streaming.
    The bot should respond with a userStream.stopped message to acknowledge.

    Args:
        message: The userStream.stop message
        websocket: The WebSocket connection to respond through
        conversation_manager: Manager for tracking active conversations

    Returns:
        A userStream.stopped response message
    """
    try:
        # Validate incoming message
        stream_stop = UserStreamStopMessage(**message)
        conversation_id = stream_stop.conversationId

        # Signal that the bot acknowledges the end of audio streaming
        logger.info(f"User stream stopping for conversation: {conversation_id}")

        # Create response
        return UserStreamStoppedResponse(
            type="userStream.stopped", conversationId=conversation_id
        )

    except ValidationError as e:
        logger.error(f"Invalid userStream.stop message: {e}")
        # Return a basic response even if validation fails
        return UserStreamStoppedResponse(type="userStream.stopped")


async def send_play_stream(
    websocket: WebSocket,
    stream_id: str,
    media_format: str,
    audio_data: bytes,
    conversation_id: Optional[str] = None,
) -> None:
    """
    Send a playStream sequence to stream audio to the user.

    The sequence consists of:
    1. playStream.start - Initiates the audio stream with a unique ID
    2. playStream.chunk - Sends the audio data encoded in base64
    3. playStream.stop - Ends the audio stream

    Only one Play Stream can be active at a time. Before starting a new stream,
    the previous one must be stopped.

    Args:
        websocket: The WebSocket connection to send through
        stream_id: A unique identifier for the Play Stream within the conversation
        media_format: The audio format (must be one of the supported formats)
        audio_data: The raw audio data to send
        conversation_id: Optional conversation ID to include in messages
    """
    # Start the stream
    start_message = PlayStreamStartMessage(
        type="playStream.start",
        streamId=stream_id,
        mediaFormat=media_format,
        conversationId=conversation_id,
    )
    logger.info(f"Starting play stream: {stream_id}")
    await websocket.send_text(start_message.json())

    # Send audio chunks
    # In a real implementation, you would chunk the audio data
    # For simplicity, we're sending it all at once here
    chunk_message = PlayStreamChunkMessage(
        type="playStream.chunk",
        streamId=stream_id,
        audioChunk=base64.b64encode(audio_data).decode("utf-8"),
        conversationId=conversation_id,
    )
    logger.debug(f"Sending audio chunk for stream: {stream_id}")
    await websocket.send_text(chunk_message.json())

    # Stop the stream
    stop_message = PlayStreamStopMessage(
        type="playStream.stop", streamId=stream_id, conversationId=conversation_id
    )
    logger.info(f"Stopping play stream: {stream_id}")
    await websocket.send_text(stop_message.json())
