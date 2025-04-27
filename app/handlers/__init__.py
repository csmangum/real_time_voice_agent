"""
Handlers module for AudioCodes WebSocket communication in the real-time voice agent.

This module provides a set of handlers for processing WebSocket messages from 
AudioCodes VoiceAI Connect Enterprise and managing the bidirectional communication 
for real-time voice conversations.

Key components:
- session_handlers: Manages WebSocket session lifecycle (initiate, resume, end) with
  AudioCodes VoiceAI Connect Enterprise.
- stream_handlers: Processes audio streaming between the bot and AudioCodes, handling
  audio chunks and stream control messages.
- activity_handlers: Processes activities like call events, DTMF inputs, and hangup
  requests, enabling call flow control.

These handlers work together to create a complete WebSocket-based voice agent that
connects AudioCodes telephony with OpenAI's Realtime API for speech-to-speech conversations.

Usage examples:
```python
# In a FastAPI WebSocket endpoint
from app.handlers import session_handlers, stream_handlers, activity_handlers
from app.models.conversation import ConversationManager

# Create a conversation manager to track active calls
conversation_manager = ConversationManager()

@app.websocket("/bot")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    
    try:
        # Process messages
        async for message_text in websocket.iter_text():
            message = json.loads(message_text)
            message_type = message.get("type", "")
            
            # Handle different message types
            if message_type == "session.initiate":
                response = await session_handlers.handle_session_initiate(
                    message, websocket, conversation_manager
                )
                await websocket.send_text(response.json())
                
            elif message_type == "userStream.chunk":
                await stream_handlers.handle_user_stream_chunk(
                    message, websocket, conversation_manager
                )
                
            elif message_type == "activities":
                await activity_handlers.handle_activities(
                    message, websocket, conversation_manager
                )
    except Exception as e:
        # Handle exceptions
        pass
"""

# Handlers module initialization 