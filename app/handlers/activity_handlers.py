"""
Handles activities from AudioCodes VoiceAI Connect Enterprise.

This module processes the 'activities' messages from AudioCodes, including call
initiation events, DTMF inputs, and hangup requests. It also provides functions
to send activities to the client for controlling call flow.
"""

import json
import logging
from typing import Any, Dict, List, Optional

from fastapi import WebSocket

from app.config.constants import LOGGER_NAME
from app.models.conversation import ConversationManager

logger = logging.getLogger(LOGGER_NAME)


async def handle_activities(
    message: Dict[str, Any],
    websocket: WebSocket,
    conversation_manager: ConversationManager,
) -> Optional[Dict[str, Any]]:
    """
    Handle the activities messages from AudioCodes VoiceAI Connect Enterprise.

    Processes various event types including call initiation, DTMF input, and hangup events.
    Activities are sent to the bot via the "activities" message containing an activities list.

    Args:
        message: The message containing the activities list and conversation ID
        websocket: The WebSocket connection to respond through
        conversation_manager: Manager for tracking active conversations

    Returns:
        None as activities typically don't require a direct response
    """
    activities = message.get("activities", [])
    conversation_id = message.get("conversationId")

    for activity in activities:
        activity_type = activity.get("type")

        if activity_type == "event":
            event_name = activity.get("name")

            if event_name == "start":
                # Handle call initiation
                logger.info(f"Call initiated for conversation: {conversation_id}")
                # No specific response needed

            elif event_name == "dtmf":
                # Handle DTMF input
                dtmf_value = activity.get("value", "")
                logger.info(
                    f"Received DTMF: {dtmf_value} for conversation: {conversation_id}"
                )
                # No specific response needed

            elif event_name == "hangup":
                logger.info(
                    f"Hangup event received for conversation: {conversation_id}"
                )
                # You might want to clean up resources here

            else:
                logger.info(f"Unhandled event type: {event_name}")
        else:
            logger.info(f"Unhandled activity type: {activity_type}")

    # Activities don't typically require a response
    return None


async def send_activities(
    websocket: WebSocket, activities: List[Dict[str, Any]]
) -> None:
    """
    Send activities to the AudioCodes VoiceAI Connect Enterprise client.

    Used to send events like playUrl for audio playback or hangup to disconnect the call.

    Args:
        websocket: The WebSocket connection to send through
        activities: List of activity objects to send
    """
    message = {"type": "activities", "activities": activities}
    logger.info(f"Sending activities: {activities}")
    await websocket.send_text(json.dumps(message))


async def hangup_call(websocket: WebSocket) -> None:
    """
    Send a hangup activity to end the call.

    When processing the hangup activity, AudioCodes VoiceAI Connect Enterprise
    will send a session.end message, disconnect the call, and close the WebSocket connection.

    Args:
        websocket: The WebSocket connection to send through
    """
    hangup_activity = [{"type": "event", "name": "hangup"}]
    logger.info("Sending hangup activity")
    await send_activities(websocket, hangup_activity)
