"""
Text to Voice Test for OpenAI Realtime API

This script allows testing the OpenAI Realtime API integration by:
1. Sending text input from the command line
2. Receiving voice output from the API
3. Saving the output as a WAV file

Usage:
    python text_to_voice_test.py [--debug] [--proxy]

Environment variables required:
    OPENAI_API_KEY: Your OpenAI API key (loaded from .env file)
"""

import asyncio
import base64
import datetime
import json
import logging
import os
import sys
import time
import wave
import argparse
from pathlib import Path
from typing import List, Optional

# Import dotenv for environment variable loading
from dotenv import load_dotenv

# Import the RealtimeAudioClient from our project
from app.bot.realtime_api import RealtimeAudioClient

# Parse command line arguments
parser = argparse.ArgumentParser(description="Test OpenAI Realtime API for text-to-voice conversion")
parser.add_argument("--debug", action="store_true", help="Enable debug logging")
parser.add_argument("--verbose", action="store_true", help="Enable verbose logging")
parser.add_argument("--proxy", action="store_true", help="Use local WebSocket proxy for debugging")
parser.add_argument("--proxy-url", type=str, default="ws://localhost:8765", help="WebSocket proxy URL")
args = parser.parse_args()

# Set log level based on command line arguments
log_level = logging.INFO
if args.debug:
    log_level = logging.DEBUG
elif args.verbose:
    log_level = logging.INFO

# Load environment variables from .env file
load_dotenv()

# Configure logging
logging.basicConfig(
    level=log_level,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("text_to_voice_test")

# Create recordings directory if it doesn't exist
RECORDINGS_DIR = Path("recordings")
RECORDINGS_DIR.mkdir(exist_ok=True)

# Audio parameters for saving WAV files
SAMPLE_RATE = 24000  # OpenAI uses 24kHz for output
SAMPLE_WIDTH = 2  # 16-bit audio
CHANNELS = 1  # Mono audio


def get_websocket_url(model: str) -> str:
    """Get the WebSocket URL to use, considering proxy settings"""
    if args.proxy:
        # Use local proxy with model as query parameter
        base_url = args.proxy_url
        url = f"{base_url}?model={model}"
        logger.info(f"Using WebSocket proxy: {url}")
    else:
        # Use direct OpenAI URL
        url = f"wss://api.openai.com/v1/realtime?model={model}"
        logger.info(f"Using direct OpenAI WebSocket: {url}")
    return url


class ProxyRealtimeAudioClient(RealtimeAudioClient):
    """Extended client that can use a WebSocket proxy for debugging"""
    
    def __init__(self, api_key: str, model: str, use_proxy: bool = False, proxy_url: str = "ws://localhost:8765"):
        super().__init__(api_key, model)
        self.use_proxy = use_proxy
        self.proxy_url = proxy_url
        
    async def connect(self) -> bool:
        """
        Connect to the OpenAI Realtime WebSocket endpoint, possibly via proxy.
        
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
        
        # Choose URL based on proxy setting
        if self.use_proxy:
            url = f"{self.proxy_url}?model={self.model}"
            logger.info(f"Connecting via WebSocket proxy: {url}")
        else:
            url = f"wss://api.openai.com/v1/realtime?model={self.model}"
            logger.info(f"Connecting directly to OpenAI: {url}")
            
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "OpenAI-Beta": "realtime=v1",
        }
        
        try:
            logger.info(f"Connecting to OpenAI Realtime API with model: {self.model}")
            logger.debug(f"WebSocket URL: {url}")
            logger.debug(f"Using headers: Authorization: Bearer [API_KEY_HIDDEN], OpenAI-Beta: realtime=v1")
            
            # Configure WebSocket with appropriate SSL settings
            import websockets
            import ssl
            
            # For proxy, we don't need SSL
            ssl_context = None if self.use_proxy else ssl.create_default_context()
            
            # Configure WebSocket for low latency
            connection_start = time.time()
            self.ws = await asyncio.wait_for(
                websockets.connect(
                    url, 
                    ssl=ssl_context,
                    max_size=16 * 1024 * 1024,  # 16MB - large enough for audio chunks
                    max_queue=32,  # Small queue to prevent buffering
                    ping_interval=5,  # 5 seconds between pings
                    ping_timeout=10,
                    compression=None,  # Disable compression for lower latency
                    additional_headers=headers
                ),
                timeout=30  # 30 seconds connection timeout
            )
            connection_time = time.time() - connection_start
            logger.debug(f"WebSocket connection established in {connection_time:.2f} seconds")
            
            # Try to optimize the socket at the TCP level if not using proxy
            if not self.use_proxy and hasattr(self.ws, "sock") and self.ws.sock:
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
            logger.error(f"Timeout while connecting to OpenAI Realtime API (after 30s)")
            self._connection_active = False
            return False
        except Exception as e:
            logger.error(f"Failed to connect to OpenAI Realtime API: {e}")
            import traceback
            logger.debug(f"Connection error details: {traceback.format_exc()}")
            self._connection_active = False
            return False


async def send_text_message(client: RealtimeAudioClient, text: str) -> bool:
    """
    Send a text message to OpenAI Realtime API.

    Args:
        client: The RealtimeAudioClient instance
        text: The text to send

    Returns:
        bool: True if the message was sent successfully
    """
    try:
        # Create a JSON message with the text
        message = {
            "role": "user", 
            "content": [
                {
                    "type": "text", 
                    "text": text
                }
            ]
        }
        message_json = json.dumps(message)
        # Convert to bytes and send
        message_bytes = message_json.encode("utf-8")
        
        logger.info(f"Sending text: {text}")
        logger.debug(f"Message JSON: {message_json}")
        return await client.send_audio_chunk(message_bytes)
    except Exception as e:
        logger.error(f"Error sending text message: {e}")
        if args.debug:
            import traceback
            logger.debug(f"Send text message error: {traceback.format_exc()}")
        return False


async def save_audio_chunks(client: RealtimeAudioClient, timeout: int = 10) -> Optional[str]:
    """
    Collect audio chunks from OpenAI and save them to a WAV file.

    Args:
        client: The RealtimeAudioClient instance
        timeout: Maximum seconds to wait for audio

    Returns:
        str: Path to the saved WAV file, or None if no audio was received
    """
    # Create a filename with timestamp
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"openai_response_{timestamp}.wav"
    filepath = RECORDINGS_DIR / filename
    
    # Collect audio chunks
    audio_chunks: List[bytes] = []
    start_time = time.time()
    last_chunk_time = start_time
    
    logger.info("Waiting for audio response...")
    
    try:
        connection_monitoring_start = time.time()
        connection_status_reported = False
        
        while time.time() - start_time < timeout:
            # Check if the connection is still active
            if not client._connection_active and not audio_chunks:
                if not connection_status_reported:
                    logger.warning("Connection lost while waiting for audio response")
                    connection_status_reported = True
                
                # Log connection state periodically for debug
                if args.debug and time.time() - connection_monitoring_start > 1:
                    logger.debug(f"Connection inactive for {time.time() - connection_monitoring_start:.1f}s")
                    connection_monitoring_start = time.time()
                
                await asyncio.sleep(0.5)  # Brief pause
                
                # If 2 seconds passed with no connection, abort
                if time.time() - start_time > 2:
                    logger.warning("Connection remained inactive, aborting audio collection")
                    break
                continue
            
            # Reset flag if connection is restored
            if client._connection_active and connection_status_reported:
                logger.info("Connection restored")
                connection_status_reported = False
                
            chunk = await client.receive_audio_chunk()
            if chunk:
                audio_chunks.append(chunk)
                # Reset the timeout when we receive data
                last_chunk_time = time.time()
                logger.debug(f"Received chunk #{len(audio_chunks)} of size {len(chunk)} bytes")
            else:
                # Small sleep to avoid CPU spinning
                await asyncio.sleep(0.01)
                
            # If we've received chunks but nothing new for 2 seconds, probably complete
            if audio_chunks and time.time() - last_chunk_time > 2:
                logger.info(f"No new audio for 2 seconds after receiving {len(audio_chunks)} chunks, assuming response complete")
                break
                
    except asyncio.CancelledError:
        logger.info("Audio collection cancelled")
    except Exception as e:
        logger.error(f"Error collecting audio: {e}")
        if args.debug:
            import traceback
            logger.debug(f"Audio collection error: {traceback.format_exc()}")
    
    # Save the audio chunks to a WAV file if we collected any
    if not audio_chunks:
        logger.warning("No audio chunks received")
        # If connection was active but no audio received, this could be an API issue
        if client._connection_active:
            logger.warning("Connection was active but no audio data received - possible API issue")
        return None
    
    try:
        # Combine all chunks
        audio_data = b"".join(audio_chunks)
        
        # Check if we actually have audio data
        if len(audio_data) < 100:  # Likely too small to be real audio
            logger.warning(f"Received too little data ({len(audio_data)} bytes), likely not valid audio")
            return None
        
        # Write WAV file
        with wave.open(str(filepath), "wb") as wav_file:
            wav_file.setnchannels(CHANNELS)
            wav_file.setsampwidth(SAMPLE_WIDTH)
            wav_file.setframerate(SAMPLE_RATE)
            wav_file.writeframes(audio_data)
        
        logger.info(f"Saved audio to {filepath} ({len(audio_data)} bytes from {len(audio_chunks)} chunks)")
        return str(filepath)
    except Exception as e:
        logger.error(f"Error saving audio file: {e}")
        if args.debug:
            import traceback
            logger.debug(f"Save audio error: {traceback.format_exc()}")
        return None


async def play_audio_file(filepath: str) -> None:
    """
    Play the audio file using system commands.

    Args:
        filepath: Path to the audio file to play
    """
    try:
        if os.name == 'nt':  # Windows
            # PowerShell command to play audio
            command = f'powershell -c "(New-Object Media.SoundPlayer \'{filepath}\').PlaySync()"'
            logger.debug(f"Playing audio with command: {command}")
            process = await asyncio.create_subprocess_shell(command)
            await process.wait()
        else:  # Linux/Mac
            # Try to detect available players
            for player in ['aplay', 'play', 'afplay']:
                try:
                    logger.debug(f"Trying audio player: {player}")
                    process = await asyncio.create_subprocess_exec(
                        player, filepath, 
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE
                    )
                    await process.wait()
                    if process.returncode == 0:
                        break
                except FileNotFoundError:
                    continue
            else:
                logger.warning("No audio player found. Please install 'aplay', 'play', or 'afplay'")
    except Exception as e:
        logger.error(f"Error playing audio: {e}")
        if args.debug:
            import traceback
            logger.debug(f"Play audio error: {traceback.format_exc()}")


async def main() -> None:
    """Run the text-to-voice test client."""
    # Get OpenAI API key
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        logger.error("OPENAI_API_KEY environment variable not set in .env file")
        sys.exit(1)
    
    # Get model name from environment or use default
    model = os.getenv("OPENAI_REALTIME_MODEL", "gpt-4o-realtime-preview-2024-12-17")
    
    # Check if using proxy
    if args.proxy:
        logger.info(f"Using WebSocket proxy at {args.proxy_url}")
        logger.info("Make sure the proxy server is running with: python ws_capture.py")
        # Create client that can use proxy
        client = ProxyRealtimeAudioClient(api_key, model, use_proxy=True, proxy_url=args.proxy_url)
    else:
        logger.info("Connecting directly to OpenAI Realtime API")
        # Use regular client
        client = RealtimeAudioClient(api_key, model)
    
    # Try to connect, with a few retries
    max_connect_attempts = 3
    connected = False
    
    for attempt in range(1, max_connect_attempts + 1):
        logger.info(f"Connection attempt {attempt}/{max_connect_attempts}")
        connected = await client.connect()
        if connected:
            break
        
        if attempt < max_connect_attempts:
            delay = 2 * attempt  # Exponential backoff
            logger.info(f"Connection failed, retrying in {delay} seconds...")
            await asyncio.sleep(delay)
    
    if not connected:
        logger.error(f"Failed to connect to OpenAI Realtime API after {max_connect_attempts} attempts")
        sys.exit(1)
    
    # Register connection event handlers
    async def on_connection_lost():
        logger.warning("Connection to OpenAI Realtime API lost")
        
    async def on_connection_restored():
        logger.info("Connection to OpenAI Realtime API restored")
        
    client.set_connection_handlers(on_connection_lost, on_connection_restored)
    
    try:
        while True:
            # Get text input from user
            try:
                text = input("\nEnter text to send (or 'q' to quit): ")
                if text.lower() in ['q', 'quit', 'exit']:
                    break
                
                # Check if connection is active, try to reconnect if not
                if not client._connection_active:
                    logger.warning("Connection not active, attempting to reconnect...")
                    reconnect_start = time.time()
                    reconnected = await client.reconnect()
                    reconnect_time = time.time() - reconnect_start
                    
                    if reconnected:
                        logger.info(f"Successfully reconnected in {reconnect_time:.2f}s")
                    else:
                        logger.error(f"Failed to reconnect to OpenAI Realtime API after {reconnect_time:.2f}s")
                        continue
                
                # Send text to OpenAI
                sent = await send_text_message(client, text)
                if not sent:
                    logger.error("Failed to send text message")
                    continue
                
                # Collect and save audio response
                filepath = await save_audio_chunks(client)
                if filepath:
                    # Play the audio response
                    await play_audio_file(filepath)
                else:
                    logger.warning("No audio response received")
                    
                    # Detailed diagnostics when no audio is received
                    if args.debug:
                        logger.debug("Connection diagnostics:")
                        logger.debug(f"  Connection active: {client._connection_active}")
                        logger.debug(f"  Reconnect attempts: {client._reconnect_attempts}")
                        logger.debug(f"  Last activity: {time.time() - client._last_activity:.1f}s ago")
                        logger.debug(f"  Audio queue size: {client.audio_queue.qsize()}")
                        
                        # Try to force a reconnection to reset the session
                        if client._connection_active:
                            logger.debug("Forcing reconnection to reset session...")
                            await client.reconnect()
            except Exception as e:
                logger.error(f"Error processing request: {e}")
                if args.debug:
                    import traceback
                    logger.debug(f"Request processing error: {traceback.format_exc()}")
                await asyncio.sleep(1)  # Brief pause before continuing
    
    finally:
        # Clean up
        logger.info("Closing connection...")
        await client.close()
        logger.info("Test client closed")


if __name__ == "__main__":
    print("OpenAI Realtime API Text-to-Voice Test")
    print("=======================================")
    print(f"Log level: {'DEBUG' if args.debug else ('INFO' if args.verbose else 'INFO')}")
    if args.proxy:
        print(f"Using WebSocket proxy: {args.proxy_url}")
    
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nTest interrupted by user")
    except Exception as e:
        logger.error(f"Unhandled error: {e}")
        if args.debug:
            import traceback
            logger.error(f"Error details: {traceback.format_exc()}") 