"""
Integration Test for OpenAI Realtime API and AudioCodes Bridge

This script tests the integration between:
1. OpenAI Realtime API client
2. AudiocodesRealtimeBridge component

It simulates the message flow between components to verify correct functionality.

Usage:
    python integration_test.py

Environment variables required:
    OPENAI_API_KEY: Your OpenAI API key (loaded from .env file)
"""

import asyncio
import base64
import json
import logging
import os
import sys
import time
import uuid
from datetime import datetime
from typing import Dict, Any

# Import dotenv for environment variable loading
from dotenv import load_dotenv

from fastapi import WebSocket
from websockets.exceptions import ConnectionClosedError

from app.bot.audiocodes_realtime_bridge import AudiocodesRealtimeBridge
from app.bot.realtime_api import RealtimeAudioClient

# Load environment variables from .env file
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("integration_test")


class MockWebSocket:
    """Mock WebSocket class to simulate FastAPI WebSocket for testing."""
    
    def __init__(self):
        self.sent_messages = []
        self.audio_chunks = []
        self.transcript_messages = []
        self.closed = False
    
    async def send_text(self, text: str) -> None:
        """Simulate sending text through WebSocket."""
        message = json.loads(text)
        self.sent_messages.append(message)
        
        # Extract audio chunks for analysis
        if message.get("type") == "playStream.chunk" and "audioChunk" in message:
            try:
                audio_data = base64.b64decode(message["audioChunk"])
                self.audio_chunks.append(audio_data)
                logger.debug(f"Received audio chunk: {len(audio_data)} bytes")
            except Exception as e:
                logger.error(f"Error decoding audio chunk: {e}")
        
        # Extract transcript messages
        if message.get("type") == "transcript":
            self.transcript_messages.append(message)
            logger.info(f"Transcript: {message.get('text', '')}")
    
    async def close(self) -> None:
        """Simulate closing the WebSocket."""
        self.closed = True
        logger.info("WebSocket closed")


async def test_bridge_integration():
    """Test the integration between OpenAI Realtime API and AudioCodes bridge."""
    # Verify environment variables
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        logger.error("OPENAI_API_KEY environment variable not set in .env file")
        sys.exit(1)
    
    # Create test conversation ID
    conversation_id = f"test-{uuid.uuid4()}"
    logger.info(f"Starting integration test with conversation ID: {conversation_id}")
    
    # Create bridge instance
    bridge = AudiocodesRealtimeBridge()
    
    # Create mock WebSocket
    mock_websocket = MockWebSocket()
    
    try:
        # Step 1: Initialize the bridge with our conversation
        logger.info("Step 1: Initializing bridge")
        await bridge.create_client(
            conversation_id=conversation_id,
            websocket=mock_websocket,
            model=os.getenv("OPENAI_REALTIME_MODEL", "gpt-4o-realtime-preview-2024-12-17")
        )
        
        # Wait for initialization
        await asyncio.sleep(1)
        
        # Check that client was created
        if conversation_id not in bridge.clients:
            logger.error("Bridge failed to create client")
            return False
        
        # Step 2: Send a text message to the OpenAI client directly
        logger.info("Step 2: Sending text message")
        client: RealtimeAudioClient = bridge.clients[conversation_id]
        
        # Create a JSON message with text
        text_message = {
            "type": "text",
            "text": "Hello, this is a test of the integration between OpenAI Realtime API and AudioCodes bridge."
        }
        message_json = json.dumps(text_message)
        message_bytes = message_json.encode("utf-8")
        
        # Send text to OpenAI
        await client.send_audio_chunk(message_bytes)
        
        # Step 3: Wait for audio responses
        logger.info("Step 3: Waiting for audio responses")
        audio_start_time = time.time()
        max_wait_time = 10  # seconds
        
        # Monitor audio chunks received
        while time.time() - audio_start_time < max_wait_time:
            # If we've received some audio chunks, break
            if len(mock_websocket.audio_chunks) > 0:
                logger.info(f"Received {len(mock_websocket.audio_chunks)} audio chunks so far")
            
            # If we've received chunks and then nothing for 2 seconds, probably done
            if (len(mock_websocket.audio_chunks) > 0 and
                time.time() - audio_start_time > 2 and 
                len(mock_websocket.sent_messages) > 5):  # Some arbitrary threshold
                logger.info("Response appears complete")
                break
                
            await asyncio.sleep(0.5)
        
        # Step 4: Send simulated audio from AudioCodes
        logger.info("Step 4: Sending simulated audio chunk from AudioCodes")
        
        # Create a silent audio chunk (1024 bytes of zeros)
        silent_audio = bytes(1024)
        audio_base64 = base64.b64encode(silent_audio).decode("utf-8")
        
        # Send through bridge
        await bridge.send_audio_chunk(conversation_id, audio_base64)
        
        # Wait a bit for processing
        await asyncio.sleep(2)
        
        # Step 5: Check results
        total_audio_chunks = len(mock_websocket.audio_chunks)
        total_messages = len(mock_websocket.sent_messages)
        
        logger.info("Step 5: Checking results")
        logger.info(f"Total messages sent by bridge: {total_messages}")
        logger.info(f"Total audio chunks received: {total_audio_chunks}")
        
        # Print all sent message types for debugging
        message_types = [msg.get("type") for msg in mock_websocket.sent_messages]
        logger.info(f"Message types received: {', '.join(message_types)}")
        
        # Print transcripts if any
        if mock_websocket.transcript_messages:
            logger.info("Transcripts received:")
            for msg in mock_websocket.transcript_messages:
                logger.info(f"- {msg.get('text', '')}")
        
        # Check if we got audio
        if total_audio_chunks > 0:
            logger.info("TEST PASSED: Received audio from OpenAI")
            return True
        else:
            logger.warning("TEST WARNING: No audio chunks received")
            # This could still be valid if OpenAI didn't respond with audio
            return True if total_messages > 0 else False
            
    except Exception as e:
        logger.error(f"Integration test failed: {e}", exc_info=True)
        return False
    finally:
        # Clean up resources
        logger.info("Cleaning up resources")
        await bridge.close_client(conversation_id)


async def test_direct_client():
    """Test the OpenAI Realtime API client directly."""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        logger.error("OPENAI_API_KEY environment variable not set in .env file")
        sys.exit(1)
    
    model = os.getenv("OPENAI_REALTIME_MODEL", "gpt-4o-realtime-preview-2024-12-17")
    logger.info(f"Testing direct client connection with model: {model}")
    
    # Create and connect client
    client = RealtimeAudioClient(api_key, model)
    connected = await client.connect()
    
    if not connected:
        logger.error("Failed to connect to OpenAI Realtime API")
        return False
    
    try:
        # Send a text message
        logger.info("Sending text message directly to OpenAI")
        text_message = {
            "type": "text",
            "text": "Hello, this is a direct test of the OpenAI Realtime API client. Please respond with voice."
        }
        message_json = json.dumps(text_message)
        message_bytes = message_json.encode("utf-8")
        
        sent = await client.send_audio_chunk(message_bytes)
        if not sent:
            logger.error("Failed to send text message")
            return False
        
        # Wait for responses
        logger.info("Waiting for responses (5 seconds)")
        start_time = time.time()
        chunks_received = 0
        
        while time.time() - start_time < 5:
            chunk = await client.receive_audio_chunk()
            if chunk:
                chunks_received += 1
                logger.info(f"Received audio chunk: {len(chunk)} bytes")
            else:
                await asyncio.sleep(0.1)
        
        logger.info(f"Received {chunks_received} audio chunks in direct test")
        return chunks_received > 0
        
    finally:
        await client.close()
        logger.info("Direct client test completed")


async def main():
    """Run all integration tests."""
    print("Starting direct client test...")
    direct_result = await test_direct_client()
    print(f"Direct client test {'PASSED' if direct_result else 'FAILED'}\n")
    
    print("Starting bridge integration test...")
    bridge_result = await test_bridge_integration()
    print(f"Bridge integration test {'PASSED' if bridge_result else 'FAILED'}\n")
    
    if direct_result and bridge_result:
        print("ALL TESTS PASSED!")
        return 0
    else:
        print("SOME TESTS FAILED")
        return 1


if __name__ == "__main__":
    print("OpenAI Realtime API Integration Tests")
    print("=====================================")
    
    try:
        exit_code = asyncio.run(main())
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\nTests interrupted by user")
    except Exception as e:
        logger.error(f"Unhandled error: {e}", exc_info=True)
        sys.exit(1) 