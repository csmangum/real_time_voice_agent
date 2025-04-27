"""
Handles audio streaming between the bot and AudioCodes VoiceAI Connect Enterprise.

This module processes audio stream control messages (start, chunk, stop) from AudioCodes
and provides functions to stream audio back to the user. It implements the audio streaming
protocol defined in the AudioCodes Bot API WebSocket mode.
"""

import asyncio
import base64
import logging
import time
from typing import Any, Dict, List, Optional

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
from app.bot.audiocodes_realtime_bridge import bridge

logger = logging.getLogger(LOGGER_NAME)

# Default chunk size for audio data (bytes)
DEFAULT_CHUNK_SIZE = 2048  # Smaller chunks for lower latency
MAX_QUEUE_SIZE = 32  # Maximum number of chunks to buffer


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

        # Ensure OpenAI client is initialized for this conversation
        if conversation_id not in bridge.clients:
            try:
                await bridge.create_client(conversation_id, websocket)
                logger.info(f"Created OpenAI Realtime client for conversation: {conversation_id}")
            except Exception as e:
                logger.error(f"Failed to initialize OpenAI client: {e}", exc_info=True)

        # Create response immediately to start receiving audio as soon as possible
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
    The audio is forwarded to OpenAI Realtime API for processing.

    Args:
        message: The userStream.chunk message containing the audioChunk in base64 encoding
        websocket: The WebSocket connection to send responses through
        conversation_manager: Manager for tracking active conversations

    Returns:
        None, as responses are handled asynchronously
    """
    try:
        # Fast path - minimal validation for speed
        audio_chunk = message.get("audioChunk")
        conversation_id = message.get("conversationId")

        if not audio_chunk or not conversation_id:
            logger.warning("Missing audio chunk or conversation ID in userStream.chunk message")
            return None

        # Get current timestamp for latency tracking
        start_time = time.time_ns() // 1_000_000  # ms

        # Forward audio chunk to OpenAI via the bridge
        # Skip full validation of the incoming message to minimize latency
        await bridge.send_audio_chunk(conversation_id, audio_chunk)
        
        # Log latency for monitoring
        processing_time = (time.time_ns() // 1_000_000) - start_time  # ms
        if processing_time > 10:  # Only log if processing took more than 10ms
            logger.debug(f"Audio chunk forwarding took {processing_time}ms for conversation: {conversation_id}")

    except Exception as e:
        logger.error(f"Error forwarding audio to OpenAI: {e}", exc_info=True)

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


def chunk_audio_data(audio_data: bytes, chunk_size: int = DEFAULT_CHUNK_SIZE) -> List[bytes]:
    """Split audio data into chunks of specified size."""
    chunks = []
    for i in range(0, len(audio_data), chunk_size):
        chunks.append(audio_data[i:i + chunk_size])
    logger.info(f"Split audio into {len(chunks)} chunks of ~{chunk_size} bytes each")
    return chunks


async def send_play_stream(
    websocket: WebSocket,
    stream_id: str,
    media_format: str,
    audio_data: bytes,
    conversation_id: Optional[str] = None,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    chunk_delay: float = 0.0,  # No delay for real-time streaming
) -> None:
    """
    Send a playStream sequence to stream audio to the user.

    The sequence consists of:
    1. playStream.start - Initiates the audio stream with a unique ID
    2. Multiple playStream.chunk - Sends the audio data in chunks, encoded in base64
    3. playStream.stop - Ends the audio stream

    Only one Play Stream can be active at a time. Before starting a new stream,
    the previous one must be stopped.

    Args:
        websocket: The WebSocket connection to send through
        stream_id: A unique identifier for the Play Stream within the conversation
        media_format: The audio format (must be one of the supported formats)
        audio_data: The raw audio data to send
        conversation_id: Optional conversation ID to include in messages
        chunk_size: Size of each audio chunk in bytes
        chunk_delay: Delay between chunks in seconds (to control streaming rate)
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

    try:
        # Split audio data into chunks
        audio_chunks = chunk_audio_data(audio_data, chunk_size)
        
        # Send each chunk with no delay for real-time streaming
        start_send_time = asyncio.get_event_loop().time()
        
        # Create tasks for sending chunks to maximize throughput
        chunk_tasks = []
        for i, chunk in enumerate(audio_chunks):
            chunk_message = PlayStreamChunkMessage(
                type="playStream.chunk",
                streamId=stream_id,
                audioChunk=base64.b64encode(chunk).decode("utf-8"),
                conversationId=conversation_id,
            )
            # Send immediately without awaiting to minimize latency
            # We'll gather the tasks later
            task = asyncio.create_task(websocket.send_text(chunk_message.json()))
            chunk_tasks.append(task)
            
            # Log progress at larger intervals to reduce logging overhead
            if i % 200 == 0 and i > 0:
                elapsed = asyncio.get_event_loop().time() - start_send_time
                logger.info(f"Sent {i}/{len(audio_chunks)} chunks ({i/len(audio_chunks)*100:.1f}%) in {elapsed:.2f} seconds")
        
        # Wait for all chunks to be sent
        if chunk_tasks:
            await asyncio.gather(*chunk_tasks)

        # Calculate and log total send time
        total_send_time = asyncio.get_event_loop().time() - start_send_time
        logger.info(f"Finished sending {len(audio_chunks)} audio chunks for stream: {stream_id} in {total_send_time:.2f} seconds")
        
        # Calculate the approximate playback rate
        audio_duration = 13.7  # Approximate duration of sample.wav in seconds
        rate_factor = audio_duration / total_send_time if total_send_time > 0 else 0
        logger.info(f"Stream rate: {rate_factor:.2f}x real-time ({audio_duration:.1f}s of audio in {total_send_time:.2f}s)")
    except Exception as e:
        logger.error(f"Error sending audio chunks: {e}", exc_info=True)
    finally:
        # Always stop the stream, even if there was an error
        stop_message = PlayStreamStopMessage(
            type="playStream.stop", streamId=stream_id, conversationId=conversation_id
        )
        logger.info(f"Stopping play stream: {stream_id}")
        await websocket.send_text(stop_message.json())
