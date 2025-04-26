import json
import logging
from typing import Dict, Any, Optional

from fastapi import WebSocket

from app.models.conversation import ConversationManager

logger = logging.getLogger("ac_server")

async def handle_session_initiate(
    message: Dict[str, Any], 
    websocket: WebSocket, 
    conversation_manager: ConversationManager
) -> Dict[str, Any]:
    """Handle the session.initiate message"""
    # Extract the supported media formats
    supported_formats = message.get("supportedMediaFormats", [])
    logger.info(f"Supported formats: {supported_formats}")
    conversation_id = message.get("conversationId")

    # Check if the required format is supported
    if "raw/lpcm16" in supported_formats:
        # Send the session.accepted response
        response = {"type": "session.accepted", "mediaFormat": "raw/lpcm16"}
        logger.info(f"Accepting session with format: raw/lpcm16")
        await websocket.send_text(json.dumps(response))
        
        # Add the conversation to the manager
        if conversation_id:
            conversation_manager.add_conversation(
                conversation_id, websocket, "raw/lpcm16"
            )
            logger.info(f"New conversation added: {conversation_id} with media format: raw/lpcm16")
            
        return response
    else:
        # If the required format is not supported, send an error
        error_response = {
            "type": "session.error",
            "reason": "Required media format not supported",
        }
        logger.warning(f"Rejecting session due to unsupported media format")
        await websocket.send_text(json.dumps(error_response))
        return error_response


async def handle_session_resume(
    message: Dict[str, Any], 
    websocket: WebSocket,
    conversation_manager: ConversationManager
) -> Dict[str, Any]:
    """Handle the session.resume message"""
    # Handle session resume similarly to session initiate
    # In a real implementation, you would restore the session state
    logger.info(f"Resuming session for conversation: {message.get('conversationId')}")
    response = {
        "type": "session.accepted",
        "mediaFormat": "raw/lpcm16",  # Ideally use the same format as before
    }
    return response


async def handle_session_end(
    message: Dict[str, Any], 
    websocket: WebSocket,
    conversation_manager: ConversationManager
) -> None:
    """Handle the session.end message"""
    conversation_id = message.get("conversationId")
    reason_code = message.get("reasonCode", "")
    reason = message.get("reason", "")
    
    logger.info(f"Session ended: {reason_code} - {reason} for conversation: {conversation_id}")
    
    # Remove the conversation from the manager
    if conversation_id:
        conversation_manager.remove_conversation(conversation_id)
        logger.info(f"Conversation removed: {conversation_id}")
        
    return None


async def handle_connection_validate(
    message: Dict[str, Any], 
    websocket: WebSocket,
    conversation_manager: ConversationManager
) -> Dict[str, Any]:
    """Handle the connection.validate message"""
    logger.info("Handling connection validation request")
    return {"type": "connection.validated", "success": True} 