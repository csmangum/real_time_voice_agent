import json
import logging
from typing import Dict, Any, Callable, Awaitable, Optional

from fastapi import WebSocket

from app.models.conversation import ConversationManager
from app.handlers.session_handlers import (
    handle_session_initiate,
    handle_session_resume,
    handle_session_end,
    handle_connection_validate,
)
from app.handlers.stream_handlers import (
    handle_user_stream_start,
    handle_user_stream_chunk,
    handle_user_stream_stop,
)
from app.handlers.activity_handlers import handle_activities

logger = logging.getLogger("ac_server")

# Type hint for handler functions
HandlerFunc = Callable[[Dict[str, Any], WebSocket, ConversationManager], Awaitable[Optional[Dict[str, Any]]]]


class WebSocketManager:
    """Manages WebSocket connections and routes messages to appropriate handlers"""
    
    def __init__(self):
        self.conversation_manager = ConversationManager()
        
        # Define handlers dictionary
        self.handlers: Dict[str, HandlerFunc] = {
            "session.initiate": handle_session_initiate,
            "session.resume": handle_session_resume,
            "userStream.start": handle_user_stream_start,
            "userStream.chunk": handle_user_stream_chunk,
            "userStream.stop": handle_user_stream_stop,
            "activities": handle_activities,
            "session.end": handle_session_end,
            "connection.validate": handle_connection_validate,
        }
        
    async def handle_websocket(self, websocket: WebSocket):
        """Handle a WebSocket connection"""
        await websocket.accept()
        logger.info("WebSocket connection established")
        conversation_id = None

        try:
            while True:
                # Receive the message
                data = await websocket.receive_text()
                message = json.loads(data)

                # Extract the conversation ID if available
                conversation_id = message.get("conversationId")
                message_type = message.get("type")

                logger.info(
                    f"Received message type: {message_type}"
                    + (f" for conversation: {conversation_id}" if conversation_id else "")
                )

                # Process the message using the appropriate handler
                if message_type in self.handlers:
                    handler = self.handlers[message_type]
                    response = await handler(message, websocket, self.conversation_manager)

                    # Special handling for session.end
                    if message_type == "session.end":
                        break  # End the WebSocket connection

                    # If the handler returned a response and hasn't sent it yet, send it now
                    if response and message_type not in [
                        "session.initiate"
                    ]:  # session.initiate handler sends its own response
                        await websocket.send_text(json.dumps(response))
                        logger.info(f"Sent response for {message_type}: {response}")
                else:
                    logger.warning(f"Unhandled message type received: {message_type}")

        except Exception as e:
            logger.error(f"Error in WebSocket connection: {e}", exc_info=True)
        finally:
            # Clean up the conversation if it exists
            if conversation_id:
                self.conversation_manager.remove_conversation(conversation_id)
                logger.info(f"Conversation removed during cleanup: {conversation_id}")
            await websocket.close()
            logger.info("WebSocket connection closed") 