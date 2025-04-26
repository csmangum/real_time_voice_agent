import json
import logging
from typing import Dict, Any, List, Optional

from fastapi import WebSocket

from app.models.conversation import ConversationManager

logger = logging.getLogger("ac_server")

async def handle_activities(
    message: Dict[str, Any], 
    websocket: WebSocket,
    conversation_manager: ConversationManager
) -> Optional[Dict[str, Any]]:
    """Handle the activities message"""
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
                logger.info(f"Received DTMF: {dtmf_value} for conversation: {conversation_id}")
                # No specific response needed

            elif event_name == "hangup":
                logger.info(f"Hangup event received for conversation: {conversation_id}")
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
    """Send activities to the client"""
    message = {"type": "activities", "activities": activities}
    logger.info(f"Sending activities: {activities}")
    await websocket.send_text(json.dumps(message))


async def hangup_call(websocket: WebSocket) -> None:
    """Send a hangup activity to end the call"""
    hangup_activity = [{"type": "event", "name": "hangup"}]
    logger.info("Sending hangup activity")
    await send_activities(websocket, hangup_activity) 