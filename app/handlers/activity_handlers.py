"""
Handles activities from AudioCodes VoiceAI Connect Enterprise.

This module processes the 'activities' messages from AudioCodes, including call
initiation events, DTMF inputs, and hangup requests. It also provides functions
to send activities to the client for controlling call flow.
"""

import base64
import logging
import os
import uuid
import wave
from typing import Any, Dict, List, Optional

from fastapi import WebSocket
from pydantic import ValidationError

from app.config.constants import LOGGER_NAME
from app.handlers.stream_handlers import send_play_stream
from app.models.conversation import ConversationManager
from app.models.message_schemas import ActivitiesMessage, ActivityEvent

logger = logging.getLogger(LOGGER_NAME)

# Path to the sample audio file
SAMPLE_WAV_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "static", "sample.wav")


def read_wav_file(file_path: str) -> bytes:
    """Read a WAV file and return its audio data."""
    logger.info(f"Reading WAV file: {file_path}")
    try:
        with wave.open(file_path, "rb") as wav_file:
            params = wav_file.getparams()
            frames = wav_file.readframes(wav_file.getnframes())
            logger.info(f"WAV parameters: {params}")
            logger.info(f"Total audio length: {len(frames)} bytes")
            return frames
    except Exception as e:
        logger.error(f"Error reading WAV file: {e}")
        return b''  # Return empty bytes if file can't be read


async def handle_activities(
    message: Dict[str, Any],
    websocket: WebSocket,
    conversation_manager: ConversationManager,
) -> Optional[None]:
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
    try:
        # Validate incoming message
        activities_message = ActivitiesMessage(**message)
        activities = activities_message.activities
        conversation_id = activities_message.conversationId

        for activity in activities:
            activity_type = activity.type

            if activity_type == "event":
                event_name = activity.name

                if event_name == "start":
                    # Handle call initiation
                    logger.info(f"Call initiated for conversation: {conversation_id}")
                    
                    # Play the sample audio file
                    await play_sample_audio(websocket, conversation_id)

                elif event_name == "dtmf":
                    # Handle DTMF input
                    dtmf_value = activity.value or ""
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

    except ValidationError as e:
        logger.error(f"Invalid activities message: {e}")
        # Try to process without validation
        activities = message.get("activities", [])
        conversation_id = message.get("conversationId")

        for activity in activities:
            activity_type = activity.get("type")

            if activity_type == "event":
                event_name = activity.get("name")
                logger.info(f"Processing unvalidated event: {event_name}")
                
                if event_name == "start" and conversation_id:
                    # Also try to play sample audio here as fallback
                    await play_sample_audio(websocket, conversation_id)

    # Activities don't typically require a response
    return None


async def play_sample_audio(websocket: WebSocket, conversation_id: str) -> None:
    """
    Load the sample.wav file and play it to the client.
    
    Args:
        websocket: The WebSocket connection to send through
        conversation_id: The conversation ID
    """
    try:
        # Check if the sample file exists
        if not os.path.exists(SAMPLE_WAV_PATH):
            logger.error(f"Sample WAV file not found at: {SAMPLE_WAV_PATH}")
            return
            
        # Get media format for this conversation
        conv_info = None
        if hasattr(websocket, "app") and hasattr(websocket.app, "conversation_manager"):
            conv_info = websocket.app.conversation_manager.get_conversation(conversation_id)
        
        # Default media format if not found in conversation
        media_format = "raw/lpcm16"
        if conv_info and "media_format" in conv_info:
            media_format = conv_info["media_format"]
            
        # Read the audio file
        audio_data = read_wav_file(SAMPLE_WAV_PATH)
        if not audio_data:
            logger.error("Failed to read sample audio data")
            return
            
        # Generate a unique stream ID
        stream_id = str(uuid.uuid4())
        
        # Stream the audio to the client
        logger.info(f"Playing sample audio to client for conversation: {conversation_id}")
        await send_play_stream(
            websocket,
            stream_id,
            media_format,
            audio_data,
            conversation_id
        )
        logger.info("Finished playing sample audio")
        
    except Exception as e:
        logger.error(f"Error playing sample audio: {e}", exc_info=True)


async def send_activities(
    websocket: WebSocket,
    activities: List[ActivityEvent],
    conversation_id: Optional[str] = None,
) -> None:
    """
    Send activities to the AudioCodes VoiceAI Connect Enterprise client.

    Used to send events like playUrl for audio playback or hangup to disconnect the call.

    Args:
        websocket: The WebSocket connection to send through
        activities: List of activity objects to send
        conversation_id: Optional conversation ID to include in message
    """
    # Create the activities message
    message = ActivitiesMessage(
        type="activities", activities=activities, conversationId=conversation_id
    )
    logger.info(f"Sending activities: {activities}")
    await websocket.send_text(message.json())


async def hangup_call(
    websocket: WebSocket, conversation_id: Optional[str] = None
) -> None:
    """
    Send a hangup activity to end the call.

    When processing the hangup activity, AudioCodes VoiceAI Connect Enterprise
    will send a session.end message, disconnect the call, and close the WebSocket connection.

    Args:
        websocket: The WebSocket connection to send through
        conversation_id: Optional conversation ID to include in message
    """
    # Create the hangup activity
    hangup_activity = [ActivityEvent(type="event", name="hangup")]
    logger.info("Sending hangup activity")
    await send_activities(websocket, hangup_activity, conversation_id)
