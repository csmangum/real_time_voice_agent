import asyncio
import base64
import json
import logging
import uuid
from datetime import UTC, datetime
from typing import Any, Dict

import websockets

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("ac_client")


async def run_bot_client():
    uri = "ws://localhost:8000/ws"
    conversation_id = str(uuid.uuid4())
    logger.info(f"Starting bot client with conversation ID: {conversation_id}")

    try:
        async with websockets.connect(uri) as websocket:
            logger.info(f"WebSocket connection established to {uri}")

            # Step 1: Session initiation
            logger.info("Step 1: Initiating session")
            await send_session_initiate(websocket, conversation_id)

            # Step 2: Simulate call initiation
            logger.info("Step 2: Simulating call initiation")
            await send_call_initiation(websocket, conversation_id)

            # Step 3: Simulate audio streaming sequence
            logger.info("Step 3: Simulating audio streaming")
            await simulate_audio_stream(websocket, conversation_id)

            # Step 4: Simulate DTMF input
            logger.info("Step 4: Simulating DTMF input")
            await send_dtmf(websocket, conversation_id, "123")

            # Step 5: End the session
            logger.info("Step 5: Ending the session")
            await send_session_end(websocket, conversation_id)

            logger.info("Bot client finished successfully")
    except Exception as e:
        logger.error(f"Error in bot client: {e}", exc_info=True)


async def send_session_initiate(websocket, conversation_id: str) -> Dict[str, Any]:
    """Send session.initiate message and return the response."""
    initiate_message = {
        "conversationId": conversation_id,
        "type": "session.initiate",
        "botName": "my_bot_name",
        "caller": "+1234567890",
        "expectAudioMessages": True,
        "supportedMediaFormats": ["raw/lpcm16"],
    }

    logger.info(f"Sending session.initiate message for conversation: {conversation_id}")
    logger.debug(f"Message content: {json.dumps(initiate_message, indent=2)}")
    await websocket.send(json.dumps(initiate_message))

    response = await websocket.recv()
    response_data = json.loads(response)
    logger.info(f"Received response to session.initiate: {response_data['type']}")
    logger.debug(f"Response content: {json.dumps(response_data, indent=2)}")

    if response_data.get("type") == "session.accepted":
        logger.info(
            f"Session accepted with media format: {response_data.get('mediaFormat')}"
        )
    else:
        logger.warning(f"Session initiation failed: {response_data}")

    return response_data


async def send_call_initiation(websocket, conversation_id: str) -> None:
    """Simulate call initiation."""
    # Use datetime with proper timezone
    timestamp = datetime.now(UTC).isoformat()

    activities_message = {
        "conversationId": conversation_id,
        "type": "activities",
        "activities": [
            {
                "type": "event",
                "name": "start",
                "id": str(uuid.uuid4()),
                "timestamp": timestamp,
                "language": "en-US",
                "parameters": {
                    "locale": "en-US",
                    "caller": "+1234567890",
                    "callee": "my_bot_name",
                },
            }
        ],
    }

    logger.info(f"Sending call initiation for conversation: {conversation_id}")
    logger.debug(f"Message content: {json.dumps(activities_message, indent=2)}")
    await websocket.send(json.dumps(activities_message))
    logger.info("Call initiation sent (no response expected)")


async def simulate_audio_stream(websocket, conversation_id: str) -> None:
    """Simulate the audio streaming sequence."""
    # Step 1: Send userStream.start
    start_message = {"conversationId": conversation_id, "type": "userStream.start"}
    logger.info(f"Starting audio stream for conversation: {conversation_id}")
    await websocket.send(json.dumps(start_message))

    # Wait for userStream.started response
    response = await websocket.recv()
    response_data = json.loads(response)
    logger.info(f"Received response to userStream.start: {response_data['type']}")
    logger.debug(f"Response content: {json.dumps(response_data, indent=2)}")

    if response_data.get("type") == "userStream.started":
        # Step 2: Send audio chunks
        logger.info("Sending audio chunks")
        # In a real scenario, these would be actual audio data
        for i in range(3):
            # Create a sample audio chunk (empty in this demo)
            audio_data = b"sample_audio_data"
            encoded_audio = base64.b64encode(audio_data).decode("utf-8")

            chunk_message = {
                "conversationId": conversation_id,
                "type": "userStream.chunk",
                "audioChunk": encoded_audio,
            }
            logger.info(f"Sending audio chunk {i+1}/3")
            await websocket.send(json.dumps(chunk_message))
            await asyncio.sleep(0.5)  # Simulate time between chunks

        # Step 3: Send userStream.stop
        stop_message = {"conversationId": conversation_id, "type": "userStream.stop"}
        logger.info(f"Stopping audio stream for conversation: {conversation_id}")
        await websocket.send(json.dumps(stop_message))

        # Wait for userStream.stopped response
        response = await websocket.recv()
        response_data = json.loads(response)
        logger.info(f"Received response to userStream.stop: {response_data['type']}")
        logger.debug(f"Response content: {json.dumps(response_data, indent=2)}")
    else:
        logger.warning(f"Failed to start audio stream: {response_data}")


async def send_dtmf(websocket, conversation_id: str, digits: str) -> None:
    """Send DTMF digits."""
    # Use datetime with proper timezone
    timestamp = datetime.now(UTC).isoformat()

    dtmf_message = {
        "conversationId": conversation_id,
        "type": "activities",
        "activities": [
            {
                "type": "event",
                "name": "dtmf",
                "id": str(uuid.uuid4()),
                "timestamp": timestamp,
                "language": "en-US",
                "value": digits,
            }
        ],
    }

    logger.info(f"Sending DTMF digits '{digits}' for conversation: {conversation_id}")
    logger.debug(f"Message content: {json.dumps(dtmf_message, indent=2)}")
    await websocket.send(json.dumps(dtmf_message))
    logger.info("DTMF digits sent (no response expected)")


async def send_session_end(websocket, conversation_id: str) -> None:
    """Send session.end message."""
    end_message = {
        "conversationId": conversation_id,
        "type": "session.end",
        "reasonCode": "client-disconnected",
        "reason": "Client Side",
    }

    logger.info(f"Ending session for conversation: {conversation_id}")
    logger.debug(f"Message content: {json.dumps(end_message, indent=2)}")
    await websocket.send(json.dumps(end_message))
    logger.info("Session end sent (no response expected)")


if __name__ == "__main__":
    logger.info("Starting AudioCodes Bot API Client")
    asyncio.run(run_bot_client())
