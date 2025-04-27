"""
Manages WebSocket session lifecycle with AudioCodes VoiceAI Connect Enterprise.

This module handles session establishment, resumption, and termination messages
from AudioCodes. It processes the session.initiate, session.resume, and session.end
messages according to the AudioCodes Bot API WebSocket protocol.
"""

import json
import logging
from typing import Any, Dict, Optional

from fastapi import WebSocket
from pydantic import ValidationError

from app.config.constants import LOGGER_NAME
from app.models.conversation import ConversationManager
from app.models.message_schemas import (
    ConnectionValidatedResponse,
    ConnectionValidateMessage,
    SessionAcceptedResponse,
    SessionEndMessage,
    SessionErrorResponse,
    SessionInitiateMessage,
    SessionResumeMessage,
)
from app.bot.audiocodes_realtime_bridge import bridge

logger = logging.getLogger(LOGGER_NAME)


async def handle_session_initiate(
    message: Dict[str, Any],
    websocket: WebSocket,
    conversation_manager: ConversationManager,
) -> SessionAcceptedResponse | SessionErrorResponse:
    """
    Handle the session.initiate message from AudioCodes VoiceAI Connect Enterprise.

    This message is sent upon establishment of the WebSocket session at the start of a call.
    The bot should respond with a session.accepted message to accept the conversation,
    or a session.error message to decline.

    The message contains critical information including:
    - conversationId: A unique identifier for the conversation
    - botName: The configured name of the bot
    - caller: The phone number of the caller
    - expectAudioMessages: Whether the bot should send audio messages
    - supportedMediaFormats: List of audio formats supported by the client

    Args:
        message: The session.initiate message with conversation details
        websocket: The WebSocket connection to respond through
        conversation_manager: Manager for tracking active conversations

    Returns:
        A session.accepted response or session.error if formats don't match
    """
    try:
        # Validate incoming message
        session_message = SessionInitiateMessage(**message)

        # Extract the supported media formats
        supported_formats = session_message.supportedMediaFormats
        logger.info(f"Supported formats: {supported_formats}")
        conversation_id = session_message.conversationId

        # Check if the required format is supported
        if "raw/lpcm16" in supported_formats:
            # Create session.accepted response
            response = SessionAcceptedResponse(
                type="session.accepted",
                mediaFormat="raw/lpcm16",
                conversationId=conversation_id,
            )
            logger.info(f"Accepting session with format: raw/lpcm16")
            await websocket.send_text(response.json())

            # Add the conversation to the manager
            if conversation_id:
                conversation_manager.add_conversation(
                    conversation_id, websocket, "raw/lpcm16"
                )
                logger.info(
                    f"New conversation added: {conversation_id} with media format: raw/lpcm16"
                )

            return response
        else:
            # If the required format is not supported, send an error
            error_response = SessionErrorResponse(
                type="session.error",
                reason="Required media format not supported",
                conversationId=conversation_id,
            )
            logger.warning(f"Rejecting session due to unsupported media format")
            await websocket.send_text(error_response.json())
            return error_response

    except ValidationError as e:
        logger.error(f"Invalid session.initiate message: {e}")
        error_response = SessionErrorResponse(
            type="session.error", reason="Invalid message format"
        )
        await websocket.send_text(error_response.json())
        return error_response


async def handle_session_resume(
    message: Dict[str, Any],
    websocket: WebSocket,
    conversation_manager: ConversationManager,
) -> SessionAcceptedResponse | SessionErrorResponse:
    """
    Handle the session.resume message from AudioCodes VoiceAI Connect Enterprise.

    This message is sent when the WebSocket connection is lost and reconnected.
    The bot should respond with a session.accepted message to resume the conversation,
    or a session.error message to decline the reconnection.

    Args:
        message: The session.resume message with the conversation ID
        websocket: The WebSocket connection to respond through
        conversation_manager: Manager for tracking active conversations

    Returns:
        A session.accepted response message
    """
    try:
        # Validate incoming message
        session_message = SessionResumeMessage(**message)
        conversation_id = session_message.conversationId

        logger.info(f"Resuming session for conversation: {conversation_id}")

        # Create the session.accepted response
        response = SessionAcceptedResponse(
            type="session.accepted",
            mediaFormat="raw/lpcm16",  # Ideally use the same format as before
            conversationId=conversation_id,
        )
        return response

    except ValidationError as e:
        logger.error(f"Invalid session.resume message: {e}")
        error_response = SessionErrorResponse(
            type="session.error", reason="Invalid message format"
        )
        await websocket.send_text(error_response.json())
        return error_response


async def handle_session_end(
    message: Dict[str, Any],
    websocket: WebSocket,
    conversation_manager: ConversationManager,
) -> None:
    """
    Handle the session.end message from AudioCodes VoiceAI Connect Enterprise.

    This message indicates the end of the conversation, typically after a hangup event.
    It includes a reason code and description for why the session ended.

    Args:
        message: The session.end message with reason details
        websocket: The WebSocket connection
        conversation_manager: Manager for tracking active conversations

    Returns:
        None, as no response is expected
    """
    try:
        # Validate incoming message
        session_end = SessionEndMessage(**message)
        conversation_id = session_end.conversationId
        reason_code = session_end.reasonCode
        reason = session_end.reason

        logger.info(
            f"Session ended: {reason_code} - {reason} for conversation: {conversation_id}"
        )

        # Close the OpenAI Realtime client for this conversation
        try:
            await bridge.close_client(conversation_id)
            logger.info(f"Closed OpenAI Realtime client for conversation: {conversation_id}")
        except Exception as e:
            logger.error(f"Error closing OpenAI client: {e}", exc_info=True)

        # Remove the conversation from the manager
        if conversation_id:
            conversation_manager.remove_conversation(conversation_id)
            logger.info(f"Conversation removed: {conversation_id}")

        return None

    except ValidationError as e:
        logger.error(f"Invalid session.end message: {e}")
        return None


async def handle_connection_validate(
    message: Dict[str, Any],
    websocket: WebSocket,
    conversation_manager: ConversationManager,
) -> ConnectionValidatedResponse:
    """
    Handle the connection.validate message from AudioCodes VoiceAI Connect Enterprise.

    This message is used to verify connectivity between the bot and AudioCodes Live Hub
    platform during initial integration. It is not part of the regular call flow.

    Args:
        message: The connection.validate message
        websocket: The WebSocket connection to respond through
        conversation_manager: Manager for tracking active conversations

    Returns:
        A connection.validated response with success=True
    """
    try:
        # Validate incoming message
        connection_message = ConnectionValidateMessage(**message)
        conversation_id = connection_message.conversationId

        logger.info("Handling connection validation request")

        # Create the connection.validated response
        return ConnectionValidatedResponse(
            type="connection.validated", success=True, conversationId=conversation_id
        )

    except ValidationError as e:
        logger.error(f"Invalid connection.validate message: {e}")
        # Even for invalid messages, we'll return a success response
        return ConnectionValidatedResponse(type="connection.validated", success=True)
