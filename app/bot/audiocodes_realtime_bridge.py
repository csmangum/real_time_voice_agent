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
from typing import Dict, Optional

from fastapi import WebSocket

from app.bot.realtime_api import RealtimeAudioClient
from app.config.constants import LOGGER_NAME

logger = logging.getLogger(LOGGER_NAME)

# Get OpenAI API key from environment variable
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
DEFAULT_MODEL = os.getenv("OPENAI_REALTIME_MODEL", "gpt-4o-realtime-preview-2024-12-17")


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
        await client.connect()
        
        # Store client and WebSocket references
        self.clients[conversation_id] = client
        self.websockets[conversation_id] = websocket
        self.stream_ids[conversation_id] = 1  # Start with stream ID 1
        
        # Start response handling task
        asyncio.create_task(self._handle_openai_responses(conversation_id))
        
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
        
        # Decode base64 audio chunk from AudioCodes
        binary_chunk = base64.b64decode(audio_chunk)
        
        # Send to OpenAI
        await client.send_audio_chunk(binary_chunk)
        logger.debug(f"Sent audio chunk to OpenAI for conversation: {conversation_id}")
    
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
            
            # Listen for audio chunks from OpenAI
            while True:
                audio_chunk = await client.receive_audio_chunk()
                
                # Send to AudioCodes as playStream.chunk
                chunk_message = {
                    "type": "playStream.chunk",
                    "streamId": str(stream_id),
                    "audioChunk": base64.b64encode(audio_chunk).decode("utf-8")
                }
                await websocket.send_text(json.dumps(chunk_message))
                logger.debug(f"Sent audio chunk to AudioCodes for conversation: {conversation_id}")
                
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
        
        if client:
            await client.close()
            logger.info(f"Closed OpenAI Realtime client for conversation: {conversation_id}")

# Create a singleton instance of the bridge
bridge = AudiocodesRealtimeBridge() 