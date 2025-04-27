import asyncio
import json
import base64
import logging
import time
from typing import Optional, Dict, Any, Callable, Awaitable

import websockets
from websockets.exceptions import ConnectionClosed, ConnectionClosedError, ConnectionClosedOK

from app.config.constants import LOGGER_NAME

logger = logging.getLogger(LOGGER_NAME)

# Constants for reconnection
MAX_RECONNECT_ATTEMPTS = 5
RECONNECT_DELAY = 2  # seconds
CONNECTION_TIMEOUT = 30  # seconds


class RealtimeAudioClient:
    """
    Client to connect to OpenAI Realtime API over WebSocket for streaming speech-to-speech.
    """
    def __init__(self, api_key: str, model: str):
        self.api_key = api_key
        self.model = model
        self.ws = None
        self.audio_queue = asyncio.Queue()
        self._recv_task = None
        self._connection_active = False
        self._reconnect_attempts = 0
        self._last_activity = 0
        self._is_closing = False
        self._connection_lost_handler: Optional[Callable[[], Awaitable[None]]] = None
        self._connection_restored_handler: Optional[Callable[[], Awaitable[None]]] = None
        
        # Start heartbeat task to monitor connection health
        self._heartbeat_task = None

    async def connect(self) -> bool:
        """
        Connect to the OpenAI Realtime WebSocket endpoint.
        
        Returns:
            bool: True if connection was successful, False otherwise
        """
        if self._is_closing:
            logger.warning("Cannot connect - client is closing")
            return False
            
        url = f"wss://api.openai.com/v1/realtime?model={self.model}"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "OpenAI-Beta": "realtime=v1",
        }
        
        try:
            logger.info(f"Connecting to OpenAI Realtime API with model: {self.model}")
            self.ws = await asyncio.wait_for(
                websockets.connect(url, extra_headers=headers),
                timeout=CONNECTION_TIMEOUT
            )
            self._connection_active = True
            self._reconnect_attempts = 0
            self._last_activity = time.time()
            
            # Start listening for responses
            if self._recv_task:
                self._recv_task.cancel()
            self._recv_task = asyncio.create_task(self._recv_loop())
            
            # Start heartbeat
            if self._heartbeat_task:
                self._heartbeat_task.cancel()
            self._heartbeat_task = asyncio.create_task(self._heartbeat())
            
            logger.info("Successfully connected to OpenAI Realtime API")
            
            # Call the connection restored handler if this was a reconnection
            if self._connection_restored_handler and self._reconnect_attempts > 0:
                await self._connection_restored_handler()
                
            return True
        except Exception as e:
            logger.error(f"Failed to connect to OpenAI Realtime API: {e}", exc_info=True)
            self._connection_active = False
            return False

    async def reconnect(self) -> bool:
        """
        Attempt to reconnect to the OpenAI Realtime API.
        
        Returns:
            bool: True if reconnection was successful, False otherwise
        """
        if self._is_closing:
            logger.warning("Cannot reconnect - client is closing")
            return False
            
        if self._reconnect_attempts >= MAX_RECONNECT_ATTEMPTS:
            logger.error(f"Max reconnection attempts ({MAX_RECONNECT_ATTEMPTS}) reached")
            return False
            
        self._reconnect_attempts += 1
        delay = RECONNECT_DELAY * self._reconnect_attempts
        
        logger.info(f"Reconnecting to OpenAI Realtime API (attempt {self._reconnect_attempts}) in {delay} seconds")
        await asyncio.sleep(delay)
        
        return await self.connect()

    async def send_audio_chunk(self, chunk: bytes) -> bool:
        """
        Send raw audio chunk bytes to OpenAI. The chunk must be in the
        supported format for the model (e.g., raw/lpcm16).
        
        Args:
            chunk: Raw audio bytes to send
            
        Returns:
            bool: True if the chunk was sent successfully, False otherwise
        """
        if not self._connection_active:
            logger.warning("Cannot send audio - connection not active")
            return False
            
        if self.ws is None or self.ws.closed:
            logger.warning("WebSocket is not connected, attempting to reconnect")
            if not await self.reconnect():
                return False
        
        try:
            await self.ws.send(chunk)
            self._last_activity = time.time()
            return True
        except ConnectionClosedError:
            logger.warning("Connection closed while sending audio, attempting to reconnect")
            if await self.reconnect():
                try:
                    await self.ws.send(chunk)
                    self._last_activity = time.time()
                    return True
                except Exception as e:
                    logger.error(f"Failed to send audio after reconnection: {e}")
                    return False
            return False
        except Exception as e:
            logger.error(f"Error sending audio chunk: {e}", exc_info=True)
            return False

    async def _recv_loop(self) -> None:
        """
        Internal loop to receive messages from OpenAI:
        audio chunks as binary or JSON messages.
        Push binary audio chunks into the audio_queue.
        """
        try:
            async for message in self.ws:
                self._last_activity = time.time()
                
                if isinstance(message, bytes):
                    # binary audio chunk
                    await self.audio_queue.put(message)
                else:
                    try:
                        data = json.loads(message)
                        
                        # Handle error messages
                        if data.get("type") == "error":
                            logger.error(f"Received error from OpenAI: {data}")
                            # Log but don't raise to keep the connection alive
                            
                        # Handle audio chunks
                        elif data.get("type") == "playStream.chunk" and data.get("audioChunk"):
                            chunk = base64.b64decode(data["audioChunk"])
                            await self.audio_queue.put(chunk)
                    except json.JSONDecodeError:
                        logger.warning(f"Received invalid JSON: {message[:100]}...")
                        
        except ConnectionClosedOK:
            logger.info("WebSocket connection closed normally")
            
        except ConnectionClosedError as e:
            logger.warning(f"WebSocket connection closed unexpectedly: {e}")
            self._connection_active = False
            
            # Notify about connection loss
            if self._connection_lost_handler:
                await self._connection_lost_handler()
                
            # Only attempt reconnection if not explicitly closing
            if not self._is_closing:
                asyncio.create_task(self.reconnect())
                
        except Exception as e:
            logger.error(f"Error in receive loop: {e}", exc_info=True)
            self._connection_active = False

    async def receive_audio_chunk(self) -> Optional[bytes]:
        """
        Await and return the next audio chunk from OpenAI.
        
        Returns:
            bytes: Audio chunk data or None if an error occurred
        """
        try:
            return await self.audio_queue.get()
        except Exception as e:
            logger.error(f"Error receiving audio chunk: {e}", exc_info=True)
            return None

    async def _heartbeat(self) -> None:
        """
        Send periodic heartbeats to keep the connection alive and monitor health.
        """
        while self._connection_active and not self._is_closing:
            await asyncio.sleep(5)  # Check every 5 seconds
            
            # Check if we haven't seen activity for too long
            if time.time() - self._last_activity > 60:  # 60 seconds
                logger.warning("No activity detected for 60 seconds, checking connection")
                
                if self.ws and not self.ws.closed:
                    try:
                        # Send a ping to test the connection
                        pong_waiter = await self.ws.ping()
                        await asyncio.wait_for(pong_waiter, timeout=5)
                        logger.debug("Ping successful, connection is healthy")
                        self._last_activity = time.time()
                    except Exception:
                        logger.warning("Ping failed, connection appears to be dead")
                        self._connection_active = False
                        
                        # Only attempt reconnection if not explicitly closing
                        if not self._is_closing:
                            asyncio.create_task(self.reconnect())
                else:
                    logger.warning("WebSocket is closed, attempting to reconnect")
                    self._connection_active = False
                    
                    # Only attempt reconnection if not explicitly closing 
                    if not self._is_closing:
                        asyncio.create_task(self.reconnect())

    def set_connection_handlers(self, 
                               lost_handler: Optional[Callable[[], Awaitable[None]]] = None,
                               restored_handler: Optional[Callable[[], Awaitable[None]]] = None) -> None:
        """
        Set handlers for connection loss and restoration events.
        
        Args:
            lost_handler: Async function to call when connection is lost
            restored_handler: Async function to call when connection is restored
        """
        self._connection_lost_handler = lost_handler
        self._connection_restored_handler = restored_handler

    async def close(self) -> None:
        """
        Close the WebSocket connection and cancel all tasks.
        """
        self._is_closing = True
        self._connection_active = False
        
        # Cancel tasks
        if self._recv_task:
            self._recv_task.cancel()
            
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
        
        # Close WebSocket
        if self.ws:
            await self.ws.close()
            
        logger.info("OpenAI Realtime client closed") 