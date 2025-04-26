"""
Manages WebSocket session lifecycle with AudioCodes VoiceAI Connect Enterprise.

This module handles session establishment, resumption, and termination messages
from AudioCodes. It processes the session.initiate, session.resume, and session.end
messages according to the AudioCodes Bot API WebSocket protocol.
"""

import json
import logging
from typing import Any, Dict

from fastapi import WebSocket

from app.config.constants import LOGGER_NAME
from app.models.conversation import ConversationManager

logger = logging.getLogger(LOGGER_NAME)


async def handle_session_initiate(
    message: Dict[str, Any],
    websocket: WebSocket,
    conversation_manager: ConversationManager,
) -> Dict[str, Any]:
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
    # Extract the supported media formats
    supported_formats = message.get("supportedMediaFormats", [])
    logger.info(f"Supported formats: {supported_formats}")
    conversation_id = message.get("conversationId")

    # Check if the required format is supported
    if "raw/lpcm16" in supported_formats:
        # Send the session.accepted response
        response = {"type": "session.accepted", "mediaFormat": "raw/lpcm16"}
        logger.info(f"Accepting session with format: raw/lpcm16")
        await websocket.send_text(json.dumps(response))

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
        error_response = {
            "type": "session.error",
            "reason": "Required media format not supported",
        }
        logger.warning(f"Rejecting session due to unsupported media format")
        await websocket.send_text(json.dumps(error_response))
        return error_response


async def handle_session_resume(
    message: Dict[str, Any],
    websocket: WebSocket,
    conversation_manager: ConversationManager,
) -> Dict[str, Any]:
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
    # Handle session resume similarly to session initiate
    # In a real implementation, you would restore the session state
    logger.info(f"Resuming session for conversation: {message.get('conversationId')}")
    response = {
        "type": "session.accepted",
        "mediaFormat": "raw/lpcm16",  # Ideally use the same format as before
    }
    return response


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
    conversation_id = message.get("conversationId")
    reason_code = message.get("reasonCode", "")
    reason = message.get("reason", "")

    logger.info(
        f"Session ended: {reason_code} - {reason} for conversation: {conversation_id}"
    )

    # Remove the conversation from the manager
    if conversation_id:
        conversation_manager.remove_conversation(conversation_id)
        logger.info(f"Conversation removed: {conversation_id}")

    return None


async def handle_connection_validate(
    message: Dict[str, Any],
    websocket: WebSocket,
    conversation_manager: ConversationManager,
) -> Dict[str, Any]:
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
    logger.info("Handling connection validation request")
    return {"type": "connection.validated", "success": True}
