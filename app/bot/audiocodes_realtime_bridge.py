"""
Bridge module for connecting AudioCodes WebSocket protocol with OpenAI Realtime API.

This module provides integration between AudioCodes VoiceAI Connect platform
and OpenAI's Realtime API, enabling real-time speech-to-speech conversations.
"""

import asyncio
import base64
import json
import logging
import os
import time
from typing import Dict, Optional

from fastapi import WebSocket

from app.bot.realtime_api import RealtimeAudioClient
from app.config.constants import LOGGER_NAME

logger = logging.getLogger(LOGGER_NAME)

# Get OpenAI API key from environment variable
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
DEFAULT_MODEL = os.getenv("OPENAI_REALTIME_MODEL", "gpt-4o-realtime-preview-2024-12-17")

# Maximum queue size for audio chunks to prevent buffering
MAX_QUEUE_SIZE = 32

class AudiocodesRealtimeBridge:
    """
    Bridge between AudioCodes WebSocket protocol and OpenAI Realtime API.
    
    This class handles:
    - Managing the lifecycle of OpenAI Realtime API connections
    - Converting between AudioCodes and OpenAI audio formats/protocols
    - Streaming audio in both directions
    """
    
    def __init__(self):
        self.clients: Dict[str, RealtimeAudioClient] = {}
        self.stream_ids: Dict[str, int] = {}  # Track stream IDs per conversation
        self.websockets: Dict[str, WebSocket] = {}
        self.response_tasks: Dict[str, asyncio.Task] = {}  # Track response handling tasks
        self.audio_latencies: Dict[str, float] = {}  # Track audio processing latency
        
    async def create_client(self, conversation_id: str, websocket: WebSocket, 
                           model: str = DEFAULT_MODEL) -> None:
        """
        Create a new OpenAI Realtime API client for a conversation.
        
        Args:
            conversation_id: The AudioCodes conversation ID
            websocket: The FastAPI WebSocket connection
            model: The OpenAI model to use
        """
        if not OPENAI_API_KEY:
            logger.error("OPENAI_API_KEY environment variable not set")
            raise ValueError("OPENAI_API_KEY environment variable not set")
        
        # Create and connect client
        client = RealtimeAudioClient(OPENAI_API_KEY, model)
        
        # Store references before connecting to capture all responses
        self.clients[conversation_id] = client
        self.websockets[conversation_id] = websocket
        self.stream_ids[conversation_id] = 1  # Start with stream ID 1
        self.audio_latencies[conversation_id] = 0.0
        
        # Connect client
        await client.connect()
        
        # Set up connection event handlers
        client.set_connection_handlers(
            lost_handler=lambda: self._handle_connection_lost(conversation_id),
            restored_handler=lambda: self._handle_connection_restored(conversation_id)
        )
        
        # Start response handling task
        self.response_tasks[conversation_id] = asyncio.create_task(
            self._handle_openai_responses(conversation_id)
        )
        
        logger.info(f"Created OpenAI Realtime client for conversation: {conversation_id}")
    
    async def send_audio_chunk(self, conversation_id: str, audio_chunk: str) -> None:
        """
        Send an audio chunk from AudioCodes to OpenAI.
        
        Args:
            conversation_id: The AudioCodes conversation ID
            audio_chunk: Base64 encoded audio data from AudioCodes
        """
        client = self.clients.get(conversation_id)
        if not client:
            logger.warning(f"No client found for conversation: {conversation_id}")
            return
        
        # Measure latency
        start_time = time.time()
        
        # Decode base64 audio chunk from AudioCodes
        # Use faster decoding approach
        try:
            binary_chunk = base64.b64decode(audio_chunk)
        except Exception as e:
            logger.error(f"Error decoding audio chunk: {e}")
            return
        
        # Send to OpenAI immediately
        await client.send_audio_chunk(binary_chunk)
        
        # Track latency for this operation
        processing_time = time.time() - start_time
        self.audio_latencies[conversation_id] = processing_time * 1000  # ms
        
        # Only log if unusually high
        if processing_time > 0.01:  # 10ms
            logger.debug(f"Audio chunk forwarding took {processing_time*1000:.2f}ms for conversation: {conversation_id}")
    
    async def _handle_connection_lost(self, conversation_id: str) -> None:
        """Handle OpenAI connection loss event."""
        logger.warning(f"OpenAI connection lost for conversation: {conversation_id}")
        
    async def _handle_connection_restored(self, conversation_id: str) -> None:
        """Handle OpenAI connection restoration event."""
        logger.info(f"OpenAI connection restored for conversation: {conversation_id}")
    
    async def _handle_openai_responses(self, conversation_id: str) -> None:
        """
        Continuously listen for audio responses from OpenAI and forward to AudioCodes.
        
        Args:
            conversation_id: The AudioCodes conversation ID
        """
        client = self.clients.get(conversation_id)
        websocket = self.websockets.get(conversation_id)
        
        if not client or not websocket:
            logger.warning(f"Missing client or websocket for conversation: {conversation_id}")
            return
        
        try:
            # First, send playStream.start message
            stream_id = self.stream_ids[conversation_id]
            start_message = {
                "type": "playStream.start",
                "streamId": str(stream_id),
                "mediaFormat": "raw/lpcm16"  # Assuming this format
            }
            await websocket.send_text(json.dumps(start_message))
            
            # Pre-encode the message type and streamId for faster message construction
            base_message = {
                "type": "playStream.chunk",
                "streamId": str(stream_id)
            }
            
            # Listen for audio chunks from OpenAI
            while True:
                # Get audio chunk with fast-path when available
                audio_chunk = await client.receive_audio_chunk()
                if not audio_chunk:
                    continue
                
                # Measure latency for processing response
                start_time = time.time()
                
                # Encode using faster approach and construct message
                audio_base64 = base64.b64encode(audio_chunk).decode("utf-8")
                
                # Construct message with minimal operations
                chunk_message = base_message.copy()
                chunk_message["audioChunk"] = audio_base64
                
                # Track per-chunk processing time
                encode_time = time.time() - start_time
                if encode_time > 0.005:  # 5ms
                    logger.debug(f"Encoding response took {encode_time*1000:.2f}ms")
                
                # Send immediately
                await websocket.send_text(json.dumps(chunk_message))
                
        except asyncio.CancelledError:
            logger.info(f"Response handling task cancelled for conversation: {conversation_id}")
        except Exception as e:
            logger.error(f"Error handling OpenAI responses: {e}", exc_info=True)
        finally:
            # Send playStream.stop message
            stop_message = {
                "type": "playStream.stop",
                "streamId": str(stream_id)
            }
            try:
                await websocket.send_text(json.dumps(stop_message))
            except Exception:
                pass  # Ignore errors during cleanup
    
    async def stop_stream(self, conversation_id: str) -> None:
        """
        Stop the audio stream for a conversation.
        
        Args:
            conversation_id: The AudioCodes conversation ID
        """
        websocket = self.websockets.get(conversation_id)
        stream_id = self.stream_ids.get(conversation_id)
        
        if websocket and stream_id:
            stop_message = {
                "type": "playStream.stop",
                "streamId": str(stream_id)
            }
            await websocket.send_text(json.dumps(stop_message))
            logger.info(f"Stopped stream for conversation: {conversation_id}")
    
    async def close_client(self, conversation_id: str) -> None:
        """
        Close the OpenAI Realtime API client for a conversation.
        
        Args:
            conversation_id: The AudioCodes conversation ID
        """
        client = self.clients.pop(conversation_id, None)
        self.websockets.pop(conversation_id, None)
        self.stream_ids.pop(conversation_id, None)
        
        # Cancel the response handling task
        task = self.response_tasks.pop(conversation_id, None)
        if task:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        
        # Report latency metrics
        avg_latency = self.audio_latencies.pop(conversation_id, 0)
        logger.info(f"Average audio processing latency for conversation {conversation_id}: {avg_latency:.2f}ms")
        
        if client:
            await client.close()
            logger.info(f"Closed OpenAI Realtime client for conversation: {conversation_id}")

# Create a singleton instance of the bridge
bridge = AudiocodesRealtimeBridge() 