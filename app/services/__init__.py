"""
Services module for external API integrations in the real-time voice agent.

This module provides client implementations and service abstractions for
communicating with external services and APIs. It handles connection management,
authentication, messaging protocols, and error handling for third-party services.

Key components:
- websocket_client: Client implementation for connecting to AudioCodes VoiceAI
  Connect Enterprise platform via WebSocket, handling message formatting and
  connection management with support for the complete AudioCodes Bot API protocol.

The services module abstracts the complexity of external API integrations,
providing clean interfaces for the rest of the application to interact with
these services while handling connection management and protocol details.

Usage examples:
```python
# Create and use the AudioCodes WebSocket client
from app.services.websocket_client import AudioCodesClient
import asyncio

async def connect_to_audiocodes():
    # Initialize the client with the WebSocket URL
    client = AudioCodesClient("wss://audiocodes-server.example.com/ws")
    
    # Connect to the server
    if await client.connect():
        # Start a new conversation session
        conversation_id = await client.initiate_session("MyBot", "+1234567890")
        
        if conversation_id:
            # Start audio streaming
            if await client.start_user_stream():
                # Send audio data
                audio_data = b"some audio bytes"  # Replace with actual audio
                await client.send_audio_chunk(audio_data)
                
                # Stop streaming when done
                await client.stop_user_stream()
            
            # End the call
            await client.send_hangup()
    
    # Close the connection
    await client.close()

# Run the async function
asyncio.run(connect_to_audiocodes())
```
"""

# Services module initialization 