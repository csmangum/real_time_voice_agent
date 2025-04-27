import asyncio
import json
import base64
import logging
import time
import traceback
from typing import Optional, Dict, Any, Callable, Awaitable

import websockets
from websockets.exceptions import ConnectionClosed, ConnectionClosedError, ConnectionClosedOK

from app.config.constants import LOGGER_NAME

logger = logging.getLogger(LOGGER_NAME)

# Constants for reconnection
MAX_RECONNECT_ATTEMPTS = 5
RECONNECT_DELAY = 2  # seconds
CONNECTION_TIMEOUT = 30  # seconds

# WebSocket configuration for low latency
WS_MAX_SIZE = 16 * 1024 * 1024  # 16MB - large enough for audio chunks
WS_MAX_QUEUE = 32  # Small queue to prevent buffering
WS_PING_INTERVAL = 5  # 5 seconds between pings


class RealtimeAudioClient:
    """
    Client to connect to OpenAI Realtime API over WebSocket for streaming speech-to-speech.
    """
    def __init__(self, api_key: str, model: str):
        self.api_key = api_key
        self.model = model
        self.ws = None
        self.audio_queue = asyncio.Queue(maxsize=WS_MAX_QUEUE)  # Limit queue size to reduce buffering
        self._recv_task = None
        self._connection_active = False
        self._reconnect_attempts = 0
        self._last_activity = 0
        self._is_closing = False
        self._connection_lost_handler: Optional[Callable[[], Awaitable[None]]] = None
        self._connection_restored_handler: Optional[Callable[[], Awaitable[None]]] = None
        
        # Start heartbeat task to monitor connection health
        self._heartbeat_task = None
        logger.info(f"RealtimeAudioClient initialized with model: {model}")

    async def connect(self) -> bool:
        """
        Connect to the OpenAI Realtime WebSocket endpoint.
        
        Returns:
            bool: True if connection was successful, False otherwise
        """
        if self._is_closing:
            logger.warning("Cannot connect - client is closing")
            return False
            
        # Reset connection active flag during connection attempt
        self._connection_active = False
        
        # Cancel any existing tasks
        if self._recv_task and not self._recv_task.done():
            logger.debug("Cancelling existing receive task")
            self._recv_task.cancel()
            try:
                await self._recv_task
            except asyncio.CancelledError:
                logger.debug("Previous receive task cancelled successfully")
            except Exception as e:
                logger.warning(f"Error while cancelling previous receive task: {e}")
        
        # Close existing WebSocket if any
        if self.ws:
            try:
                logger.debug("Closing existing WebSocket connection")
                await self.ws.close()
            except Exception as e:
                logger.warning(f"Error closing existing WebSocket: {e}")
            self.ws = None
            
        url = f"wss://api.openai.com/v1/realtime?model={self.model}"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "OpenAI-Beta": "realtime=v1",
        }
        
        try:
            logger.info(f"Connecting to OpenAI Realtime API with model: {self.model}")
            logger.debug(f"WebSocket URL: {url}")
            logger.debug(f"Using headers: Authorization: Bearer [API_KEY_HIDDEN], OpenAI-Beta: realtime=v1")
            
            # Configure WebSocket for low latency with:
            # - max_size: Large enough for audio chunks
            # - max_queue: Small to prevent buffering
            # - ping_interval: Frequent enough for connection validation
            # - compression: None to avoid compression overhead
            connection_start = time.time()
            self.ws = await asyncio.wait_for(
                websockets.connect(
                    url, 
                    max_size=WS_MAX_SIZE,
                    max_queue=WS_MAX_QUEUE,
                    ping_interval=WS_PING_INTERVAL,
                    ping_timeout=10,
                    compression=None,  # Disable compression for lower latency
                    additional_headers=headers
                ),
                timeout=CONNECTION_TIMEOUT
            )
            connection_time = time.time() - connection_start
            logger.debug(f"WebSocket connection established in {connection_time:.2f} seconds")
            
            # Try to optimize the socket at the TCP level
            if hasattr(self.ws, "sock") and self.ws.sock:
                import socket
                try:
                    # Disable Nagle's algorithm to send packets immediately
                    self.ws.sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                    logger.info("Optimized OpenAI socket: TCP_NODELAY enabled for low latency")
                except Exception as e:
                    logger.warning(f"Could not optimize OpenAI socket: {e}")
            
            self._connection_active = True
            self._reconnect_attempts = 0
            self._last_activity = time.time()
            
            # Start listening for responses
            logger.debug("Starting WebSocket receive loop")
            self._recv_task = asyncio.create_task(self._recv_loop())
            
            # Start heartbeat
            if self._heartbeat_task and not self._heartbeat_task.done():
                logger.debug("Cancelling existing heartbeat task")
                self._heartbeat_task.cancel()
                try:
                    await self._heartbeat_task
                except asyncio.CancelledError:
                    logger.debug("Previous heartbeat task cancelled successfully")
                except Exception as e:
                    logger.warning(f"Error while cancelling previous heartbeat task: {e}")
            
            logger.debug("Starting heartbeat task")
            self._heartbeat_task = asyncio.create_task(self._heartbeat())
            
            logger.info("Successfully connected to OpenAI Realtime API")
            
            # Call the connection restored handler if this was a reconnection
            if self._connection_restored_handler and self._reconnect_attempts > 0:
                logger.debug("Calling connection restored handler")
                await self._connection_restored_handler()
                
            return True
        except asyncio.TimeoutError:
            logger.error(f"Timeout while connecting to OpenAI Realtime API (after {CONNECTION_TIMEOUT}s)")
            self._connection_active = False
            return False
        except Exception as e:
            logger.error(f"Failed to connect to OpenAI Realtime API: {e}")
            logger.debug(f"Connection error details: {traceback.format_exc()}")
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
        
        logger.info(f"Reconnecting to OpenAI Realtime API (attempt {self._reconnect_attempts}/{MAX_RECONNECT_ATTEMPTS}) in {delay} seconds")
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
            
        if self.ws is None:
            logger.warning("WebSocket is not connected, attempting to reconnect")
            if not await self.reconnect():
                return False
        
        try:
            # Log message details when sending text
            try:
                if len(chunk) < 1000:  # Only try to decode small chunks that might be text messages
                    message_text = chunk.decode('utf-8')
                    if message_text.startswith('{') and message_text.endswith('}'):
                        logger.debug(f"Sending message: {message_text}")
            except Exception:
                # Not text data, just log the size
                logger.debug(f"Sending binary chunk of size {len(chunk)} bytes")
            
            # Use a timeout to prevent getting stuck
            send_start = time.time()
            await asyncio.wait_for(self.ws.send(chunk), timeout=5.0)
            send_time = time.time() - send_start
            logger.debug(f"Sent message in {send_time:.4f} seconds")
            self._last_activity = time.time()
            return True
        except asyncio.TimeoutError:
            logger.warning("Timeout while sending audio chunk")
            self._connection_active = False
            # Try to reconnect
            if await self.reconnect():
                try:
                    logger.debug("Retrying send after reconnection")
                    await asyncio.wait_for(self.ws.send(chunk), timeout=5.0)
                    self._last_activity = time.time()
                    return True
                except Exception as e:
                    logger.error(f"Failed to send audio after reconnection: {e}")
                    return False
            return False
        except ConnectionClosedOK:
            logger.info("Connection closed normally while sending audio")
            self._connection_active = False
            # Try to reconnect
            if await self.reconnect():
                try:
                    logger.debug("Retrying send after reconnection")
                    await asyncio.wait_for(self.ws.send(chunk), timeout=5.0)
                    self._last_activity = time.time()
                    return True
                except Exception as e:
                    logger.error(f"Failed to send audio after reconnection: {e}")
                    return False
            return False
        except ConnectionClosedError as e:
            logger.warning(f"Connection closed while sending audio: {e}")
            self._connection_active = False
            if await self.reconnect():
                try:
                    logger.debug("Retrying send after reconnection")
                    await asyncio.wait_for(self.ws.send(chunk), timeout=5.0)
                    self._last_activity = time.time()
                    return True
                except Exception as e:
                    logger.error(f"Failed to send audio after reconnection: {e}")
                    return False
            return False
        except Exception as e:
            logger.error(f"Error sending audio chunk: {e}")
            logger.debug(f"Send error details: {traceback.format_exc()}")
            return False

    async def _recv_loop(self) -> None:
        """
        Internal loop to receive messages from OpenAI:
        audio chunks as binary or JSON messages.
        Push binary audio chunks into the audio_queue.
        """
        if not self.ws:
            logger.error("WebSocket not initialized for receive loop")
            self._connection_active = False
            return
        
        try:
            logger.debug("Receive loop started")
            while self._connection_active and not self._is_closing:
                try:
                    # Use a timeout to prevent blocking indefinitely
                    logger.debug("Waiting for message from OpenAI...")
                    recv_start = time.time()
                    message = await asyncio.wait_for(self.ws.recv(), timeout=5.0)
                    recv_time = time.time() - recv_start
                    self._last_activity = time.time()
                    
                    if isinstance(message, bytes):
                        # binary audio chunk - put directly into queue without additional processing
                        logger.debug(f"Received binary chunk of size {len(message)} bytes in {recv_time:.4f}s")
                        await self.audio_queue.put(message)
                        logger.debug(f"Audio queue size: {self.audio_queue.qsize()}/{self.audio_queue.maxsize}")
                    else:
                        try:
                            logger.debug(f"Received text message in {recv_time:.4f}s: {message[:200]}...")
                            data = json.loads(message)
                            
                            # Handle error messages
                            if data.get("type") == "error":
                                logger.error(f"Received error from OpenAI: {data}")
                                # Log but don't raise to keep the connection alive
                                
                            # Handle audio chunks
                            elif data.get("type") == "playStream.chunk" and data.get("audioChunk"):
                                chunk = base64.b64decode(data["audioChunk"])
                                logger.debug(f"Decoded audio chunk of size {len(chunk)} bytes")
                                await self.audio_queue.put(chunk)
                                logger.debug(f"Audio queue size after adding chunk: {self.audio_queue.qsize()}/{self.audio_queue.maxsize}")
                            else:
                                # Log other message types for debugging
                                logger.debug(f"Received message of type: {data.get('type', 'unknown')}")
                        except json.JSONDecodeError:
                            logger.warning(f"Received invalid JSON: {message[:100]}...")
                except asyncio.TimeoutError:
                    # This is expected - just continue the loop
                    logger.debug("Receive timeout - no message received within 5s")
                    continue
                except ConnectionClosedOK:
                    # Normal closure, don't treat as error
                    logger.info("WebSocket connection closed normally")
                    self._connection_active = False
                    break
                except ConnectionClosedError as e:
                    logger.warning(f"Connection closed during receive: {e}")
                    logger.debug(f"WebSocket close code: {e.code}, reason: {e.reason}")
                    self._connection_active = False
                    break
                except Exception as e:
                    logger.error(f"Error in receive loop iteration: {e}")
                    logger.debug(f"Receive error details: {traceback.format_exc()}")
                    await asyncio.sleep(0.1)  # Brief pause to avoid tight looping on errors
                            
        except ConnectionClosedOK:
            # Normal closure
            logger.info("WebSocket connection closed normally")
            
        except ConnectionClosedError as e:
            logger.warning(f"WebSocket connection closed unexpectedly: {e}")
            logger.debug(f"WebSocket close code: {e.code}, reason: {e.reason}")
            
        except Exception as e:
            logger.error(f"Error in receive loop: {e}")
            logger.debug(f"Receive loop error details: {traceback.format_exc()}")
            
        # Mark connection as inactive
        self._connection_active = False
        logger.info("Receive loop exited, connection marked as inactive")
        
        # Notify about connection loss
        if self._connection_lost_handler:
            try:
                logger.debug("Calling connection lost handler")
                await self._connection_lost_handler()
            except Exception as e:
                logger.error(f"Error in connection lost handler: {e}")
                logger.debug(f"Connection lost handler error details: {traceback.format_exc()}")
            
        # Only attempt reconnection if not explicitly closing
        if not self._is_closing:
            logger.debug("Scheduling reconnection attempt")
            asyncio.create_task(self.reconnect())

    async def receive_audio_chunk(self) -> Optional[bytes]:
        """
        Await and return the next audio chunk from OpenAI.
        
        Returns:
            bytes: Audio chunk data or None if an error occurred
        """
        try:
            # Use get_nowait when available to avoid waiting for chunks that might never come
            if not self.audio_queue.empty():
                chunk = self.audio_queue.get_nowait()
                logger.debug(f"Retrieved audio chunk of size {len(chunk) if chunk else 0} bytes from queue immediately")
                return chunk
            
            # If queue is empty but connection is not active, return None
            if not self._connection_active:
                logger.debug("Audio queue empty and connection not active, returning None")
                return None
            
            # Wait for data with timeout to prevent blocking forever
            logger.debug("Waiting for audio data...")
            chunk = await asyncio.wait_for(self.audio_queue.get(), timeout=2.0)
            logger.debug(f"Retrieved audio chunk of size {len(chunk) if chunk else 0} bytes from queue after waiting")
            return chunk
        except asyncio.TimeoutError:
            # This is expected if no data is coming
            logger.debug("Timeout waiting for audio chunk")
            return None
        except Exception as e:
            logger.error(f"Error receiving audio chunk: {e}")
            logger.debug(f"Receive audio chunk error details: {traceback.format_exc()}")
            return None

    async def _heartbeat(self) -> None:
        """
        Send periodic heartbeats to keep the connection alive and monitor health.
        """
        logger.debug("Heartbeat task started")
        while self._connection_active and not self._is_closing:
            await asyncio.sleep(5)  # Check every 5 seconds
            
            # Check if we haven't seen activity for too long
            inactivity_period = time.time() - self._last_activity
            if inactivity_period > 60:  # 60 seconds
                logger.warning(f"No activity detected for {inactivity_period:.1f} seconds, checking connection")
                
                if self.ws:
                    try:
                        # Send a ping to test the connection
                        logger.debug("Sending ping to test connection")
                        ping_start = time.time()
                        pong_waiter = await self.ws.ping()
                        await asyncio.wait_for(pong_waiter, timeout=5)
                        ping_time = time.time() - ping_start
                        logger.debug(f"Ping successful in {ping_time:.4f}s, connection is healthy")
                        self._last_activity = time.time()
                    except Exception as e:
                        logger.warning(f"Ping failed: {e}, connection appears to be dead")
                        self._connection_active = False
                        
                        # Only attempt reconnection if not explicitly closing
                        if not self._is_closing:
                            logger.debug("Scheduling reconnection after failed ping")
                            asyncio.create_task(self.reconnect())
                else:
                    logger.warning("WebSocket is closed, attempting to reconnect")
                    self._connection_active = False
                    
                    # Only attempt reconnection if not explicitly closing 
                    if not self._is_closing:
                        logger.debug("Scheduling reconnection for closed WebSocket")
                        asyncio.create_task(self.reconnect())
        
        logger.debug("Heartbeat task exited")

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
        logger.debug("Connection event handlers registered")

    async def close(self) -> None:
        """
        Close the WebSocket connection and cancel all tasks.
        """
        logger.info("Closing OpenAI Realtime client")
        self._is_closing = True
        self._connection_active = False
        
        # Cancel tasks
        if self._recv_task:
            logger.debug("Cancelling receive task")
            self._recv_task.cancel()
            
        if self._heartbeat_task:
            logger.debug("Cancelling heartbeat task")
            self._heartbeat_task.cancel()
        
        # Close WebSocket
        if self.ws:
            logger.debug("Closing WebSocket connection")
            await self.ws.close()
            
        logger.info("OpenAI Realtime client closed") 