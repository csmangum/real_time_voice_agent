"""
Bot module for integrating OpenAI Realtime API with AudioCodes VoiceAI Connect.

This module provides components for real-time speech-to-speech conversations
by connecting the AudioCodes WebSocket protocol with OpenAI's Realtime API.

Key components:
- RealtimeAudioClient: Client for connecting to OpenAI's Realtime API over WebSockets
  to stream audio in both directions with features like auto-reconnection and heartbeats.
- AudiocodesRealtimeBridge: Bidirectional bridge that handles protocol conversion between
  AudioCodes VoiceAI Connect platform and OpenAI's Realtime API, including audio format
  conversion and stream management.

This module is the core of the voice agent system, enabling real-time voice conversations
with OpenAI's models through AudioCodes telephony infrastructure.

Usage examples:
```python
# Using the singleton bridge instance (recommended for most cases)
from app.bot import bridge
import asyncio

async def handle_new_conversation(conversation_id, websocket):
    # Create a new client for this conversation
    await bridge.create_client(conversation_id, websocket)
    
    # Send audio to OpenAI
    await bridge.send_audio_chunk(conversation_id, base64_audio_data)
    
    # Clean up when conversation ends
    await bridge.close_client(conversation_id)

# Direct usage of RealtimeAudioClient (for custom implementations)
from app.bot import RealtimeAudioClient
import os

async def custom_client_usage():
    # Create and connect client
    api_key = os.getenv("OPENAI_API_KEY")
    model = "gpt-4o-realtime-preview-2024-12-17"
    client = RealtimeAudioClient(api_key, model)
    await client.connect()
    
    # Send and receive audio
    await client.send_audio_chunk(audio_bytes)
    response_chunk = await client.receive_audio_chunk()
    
    # Close when done
    await client.close()
```
"""

from app.bot.realtime_api import RealtimeAudioClient
from app.bot.audiocodes_realtime_bridge import bridge, AudiocodesRealtimeBridge

__all__ = ["RealtimeAudioClient", "bridge", "AudiocodesRealtimeBridge"]
