import asyncio
import base64
import json
import logging
import os
import uuid
import wave
from datetime import UTC, datetime
from typing import Dict, List

import websockets

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("ac_simple_client")


async def run_simple_client(save_audio=False):
    """
    A simple client that:
    1. Connects to the server
    2. Initiates a session
    3. Sends a call start event
    4. Receives audio from the server
    5. Disconnects cleanly

    Args:
        save_audio (bool): Whether to save received audio as a WAV file
    """
    uri = "ws://localhost:8000/ws"
    conversation_id = str(uuid.uuid4())
    logger.info(f"Starting simple client with conversation ID: {conversation_id}")

    try:
        async with websockets.connect(uri) as websocket:
            logger.info(f"WebSocket connection established to {uri}")

            # Step 1: Session initiation
            logger.info("Step 1: Initiating session")
            await initiate_session(websocket, conversation_id)

            # Step 2: Send call start event to trigger audio streaming
            logger.info("Step 2: Sending call start event")
            await send_call_start(websocket, conversation_id)

            # Step 3: Receive and process server messages (including audio)
            logger.info("Step 3: Receiving server messages")
            await receive_messages(websocket, conversation_id, save_audio)

            logger.info("Client finished successfully")
    except Exception as e:
        logger.error(f"Error in client: {e}", exc_info=True)


async def initiate_session(websocket, conversation_id: str) -> None:
    """Initiate a session with the server."""
    initiate_message = {
        "conversationId": conversation_id,
        "type": "session.initiate",
        "botName": "my_bot_name",
        "caller": "+1234567890",
        "expectAudioMessages": True,
        "supportedMediaFormats": [
            "wav/lpcm16",
            "wav/lpcm24",
            "raw/lpcm16",
            "raw/lpcm24",
        ],
    }

    logger.info(
        f"Sending session.initiate message with supported formats: {initiate_message['supportedMediaFormats']}"
    )
    await websocket.send(json.dumps(initiate_message))

    # Wait for session.accepted response
    response = await websocket.recv()
    response_data = json.loads(response)

    if response_data.get("type") == "session.accepted":
        media_format = response_data.get("mediaFormat")
        logger.info(f"Session accepted with format: {media_format}")

        # Log important information about the format for debugging
        if media_format:
            if "wav" in media_format:
                logger.info("Server will send audio in WAV format with headers")
            elif "raw" in media_format:
                logger.info("Server will send raw PCM audio without headers")

            if "lpcm16" in media_format:
                logger.info("Audio format uses 16-bit samples")
            elif "lpcm24" in media_format:
                logger.info("Audio format uses 24-bit samples")
    else:
        logger.warning(f"Unexpected response: {response_data}")


async def send_call_start(websocket, conversation_id: str) -> None:
    """Send a call start event to trigger audio streaming."""
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

    logger.info("Sending call start event")
    await websocket.send(json.dumps(activities_message))


async def receive_messages(
    websocket, conversation_id: str, save_audio: bool = False
) -> None:
    """
    Receive and handle messages from the server until the audio stream is complete
    or a timeout occurs.

    Args:
        websocket: The WebSocket connection
        conversation_id: The conversation ID
        save_audio: Whether to save received audio as a WAV file
    """
    active_stream_id = None
    chunks_received = 0
    active_streams = set()

    # Set a timeout (15 seconds - should be enough for the 13 second audio file)
    start_time = asyncio.get_event_loop().time()
    timeout = 15

    # Audio collection - store chunks if save_audio is True
    audio_chunks = [] if save_audio else None
    media_format = None
    total_audio_bytes = 0
    first_chunk_received = False

    try:
        while True:
            # Check for timeout
            if asyncio.get_event_loop().time() - start_time > timeout:
                logger.info(f"Timeout reached after {timeout} seconds")
                break

            # Use wait_for with a short timeout to be able to check our conditions
            try:
                message = await asyncio.wait_for(websocket.recv(), timeout=1.0)
            except asyncio.TimeoutError:
                # No message received within 1 second
                # If we've received some audio chunks and there's no active stream,
                # we can assume the audio is complete
                if chunks_received > 0 and len(active_streams) == 0:
                    logger.info(
                        "No active streams and received chunks > 0, assuming audio complete"
                    )
                    break
                continue

            message_data = json.loads(message)
            message_type = message_data.get("type")

            # Handle different message types
            if message_type == "playStream.start":
                stream_id = message_data.get("streamId")
                media_format = message_data.get("mediaFormat")
                active_streams.add(stream_id)
                logger.info(
                    f"Server started audio stream: {stream_id} in format {media_format}"
                )

            elif message_type == "playStream.chunk":
                stream_id = message_data.get("streamId")
                if stream_id in active_streams:
                    audio_chunk = message_data.get("audioChunk", "")
                    try:
                        decoded = base64.b64decode(audio_chunk)
                        chunks_received += 1
                        total_audio_bytes += len(decoded)

                        # Analyze first chunk to detect potential issues
                        if not first_chunk_received and decoded:
                            first_chunk_received = True
                            analyze_audio_chunk(decoded, media_format)

                        if save_audio:
                            audio_chunks.append(decoded)
                        if chunks_received % 100 == 0:  # Log every 100 chunks
                            logger.info(
                                f"Received {chunks_received} audio chunks ({total_audio_bytes} bytes) so far"
                            )
                    except Exception as e:
                        logger.error(f"Failed to decode audio chunk: {e}")

            elif message_type == "playStream.stop":
                stream_id = message_data.get("streamId")
                if stream_id in active_streams:
                    active_streams.remove(stream_id)
                    logger.info(f"Server stopped audio stream: {stream_id}")
                    # If we've received chunks and all streams are closed, we're done
                    if chunks_received > 0 and len(active_streams) == 0:
                        logger.info(
                            f"Audio streaming complete, received {chunks_received} chunks ({total_audio_bytes} bytes)"
                        )
                        # Save audio if requested
                        if save_audio and audio_chunks:
                            save_wav_file(audio_chunks, conversation_id, media_format)
                        # Send session end to cleanly disconnect
                        await send_session_end(websocket, conversation_id)
                        break
            else:
                logger.debug(f"Received message type: {message_type}")

    except Exception as e:
        logger.error(f"Error while receiving messages: {e}", exc_info=True)
        # Make sure we clean up by ending the session
        try:
            await send_session_end(websocket, conversation_id)
        except:
            pass


def analyze_audio_chunk(chunk: bytes, media_format: str) -> None:
    """
    Analyze an audio chunk to detect potential issues with the format.

    Args:
        chunk: The audio chunk to analyze
        media_format: The reported media format
    """
    try:
        # Log chunk size and first few bytes
        logger.info(f"First audio chunk size: {len(chunk)} bytes")
        logger.info(f"First 32 bytes (hex): {chunk[:32].hex(' ')}")

        # Analyze byte pattern
        if len(chunk) >= 44:  # Minimum WAV header size
            # Check for WAV header (RIFF....WAVE)
            if chunk.startswith(b"RIFF") and b"WAVE" in chunk[:16]:
                logger.warning(
                    "CRITICAL ISSUE: Audio chunk contains a complete WAV header!"
                )
                logger.warning(
                    "The server is sending WAV file format but we're processing as raw PCM"
                )

                # Try to extract WAV header information
                try:
                    # Check format chunk (should start with "fmt " after the RIFF header)
                    fmt_pos = chunk.find(b"fmt ")
                    if fmt_pos > 0 and fmt_pos + 24 <= len(chunk):
                        # Format data starts 8 bytes after "fmt " (skipping chunk size)
                        format_data = chunk[fmt_pos + 8 : fmt_pos + 24]

                        # Extract format values (assuming standard PCM format)
                        audio_format = int.from_bytes(
                            format_data[0:2], byteorder="little"
                        )  # 1 = PCM
                        num_channels = int.from_bytes(
                            format_data[2:4], byteorder="little"
                        )
                        sample_rate = int.from_bytes(
                            format_data[4:8], byteorder="little"
                        )
                        byte_rate = int.from_bytes(
                            format_data[8:12], byteorder="little"
                        )
                        block_align = int.from_bytes(
                            format_data[12:14], byteorder="little"
                        )
                        bits_per_sample = int.from_bytes(
                            format_data[14:16], byteorder="little"
                        )

                        logger.info(
                            f"Extracted WAV header info: format={audio_format}, channels={num_channels}, "
                            f"sample_rate={sample_rate}Hz, bits={bits_per_sample}"
                        )

                        # Check for data chunk, which contains the actual audio data
                        data_pos = chunk.find(b"data")
                        if data_pos > 0 and data_pos + 8 <= len(chunk):
                            data_size = int.from_bytes(
                                chunk[data_pos + 4 : data_pos + 8], byteorder="little"
                            )
                            data_start = data_pos + 8
                            logger.info(
                                f"Audio data starts at byte {data_start}, declared size: {data_size} bytes"
                            )

                            # Calculate expected duration
                            if sample_rate > 0 and block_align > 0:
                                expected_duration = data_size / (
                                    sample_rate * block_align
                                )
                                logger.info(
                                    f"Expected audio duration from header: {expected_duration:.2f} seconds"
                                )

                        return  # Exit after analyzing WAV header
                except Exception as e:
                    logger.error(f"Error parsing WAV header: {e}")

            # Check if first bytes suggest an audio format issue
            if all(b == 0 for b in chunk[:10]):
                logger.warning(
                    "First bytes are all zero - possible format mismatch or empty audio"
                )

            # Analyze patterns in audio samples for 16-bit PCM
            if len(chunk) >= 100:
                # Skip potential WAV header, analyze the audio data portion
                data_offset = 0
                if chunk.find(b"data") > 0:
                    possible_data_pos = chunk.find(b"data")
                    if possible_data_pos > 0 and possible_data_pos + 8 < len(chunk):
                        data_offset = possible_data_pos + 8

                # Extract some samples for analysis
                samples = []
                sample_count = 50
                for i in range(data_offset, data_offset + sample_count * 2, 2):
                    if i + 1 < len(chunk):
                        # Assume little-endian 16-bit PCM
                        sample = int.from_bytes(
                            chunk[i : i + 2], byteorder="little", signed=True
                        )
                        samples.append(sample)

                if samples:
                    # Log some statistics
                    max_val = max(samples, key=abs)
                    avg_val = sum(abs(s) for s in samples) / len(samples)

                    logger.info(
                        f"Audio statistics: max_amplitude={max_val}, avg_amplitude={avg_val:.2f}"
                    )

                    # Check if all samples are very small (potential issue)
                    if all(abs(s) < 100 for s in samples):
                        logger.warning(
                            "All samples have very low amplitude - possible format mismatch"
                        )

                    # Count sign changes (zero crossings) - very low or high could indicate issues
                    sign_changes = sum(
                        1
                        for i in range(1, len(samples))
                        if (samples[i - 1] >= 0) != (samples[i] >= 0)
                    )
                    zero_crossing_rate = (
                        sign_changes / (len(samples) - 1) if len(samples) > 1 else 0
                    )
                    logger.info(f"Zero crossing rate: {zero_crossing_rate:.3f}")

                    # Extremely high zero crossing rate might indicate noise or format issues
                    if zero_crossing_rate > 0.7:
                        logger.warning(
                            "Very high zero crossing rate - possible noise or incorrect format"
                        )

        # Based on media format string, suggest appropriate settings
        if media_format:
            logger.info(f"Media format reported by server: {media_format}")

    except Exception as e:
        logger.error(f"Error analyzing audio chunk: {e}", exc_info=True)


def save_wav_file(audio_chunks, conversation_id, media_format):
    """
    Save the collected audio chunks as a WAV file.

    Args:
        audio_chunks: List of audio data chunks
        conversation_id: The conversation ID to use in the filename
        media_format: The format of the audio data
    """
    try:
        # Create output directory if it doesn't exist
        output_dir = "recordings"
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)

        # Create filename with timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{output_dir}/{timestamp}_{conversation_id[-8:]}.wav"

        # Concatenate all audio chunks
        audio_data = b"".join(audio_chunks)

        # Log the total size of the audio data
        logger.info(f"Total audio data size: {len(audio_data)} bytes")

        # EXACT parameters from the sample.wav file on the server
        # (visible in server logs)
        channels = 2  # Stereo
        sample_width = 3  # 24-bit
        framerate = 44100  # 44.1kHz

        logger.info(
            f"Using WAV parameters: channels={channels}, sample_width={sample_width}, framerate={framerate}"
        )

        # Create the output file
        with wave.open(filename, "wb") as wav_file:
            wav_file.setnchannels(channels)
            wav_file.setsampwidth(sample_width)
            wav_file.setframerate(framerate)
            wav_file.writeframes(audio_data)

        logger.info(f"Saved audio to {filename}")

        # Calculate expected duration
        bytes_per_frame = channels * sample_width
        num_frames = len(audio_data) // bytes_per_frame
        duration_seconds = num_frames / framerate
        logger.info(f"Expected audio duration: {duration_seconds:.2f} seconds")

    except Exception as e:
        logger.error(f"Failed to save WAV file: {e}", exc_info=True)


async def send_session_end(websocket, conversation_id: str) -> None:
    """Send session.end message to cleanly disconnect."""
    try:
        end_message = {
            "conversationId": conversation_id,
            "type": "session.end",
            "reasonCode": "client-disconnected",
            "reason": "Client Side",
        }

        logger.info("Ending session")
        await websocket.send(json.dumps(end_message))
    except Exception as e:
        logger.error(f"Error ending session: {e}")


if __name__ == "__main__":
    logger.info("Starting Simple AudioCodes Bot API Client")
    # To save audio, set save_audio to True
    asyncio.run(run_simple_client(save_audio=True))
