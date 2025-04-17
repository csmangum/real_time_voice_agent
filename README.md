# AudioCodes Streaming Bot API - POC

This project demonstrates a proof-of-concept integration with AudioCodes VoiceAI Connect using the WebSocket-based Voice Bot API protocol. The project has two main components:

1. A WebRTC-based audio streaming server (for capturing audio)
2. An AudioCodes WebSocket server endpoint that implements their Bot API protocol

## Overview

AudioCodes VoiceAI Connect Enterprise is a platform that can route phone calls to voice bots. This POC implements the server-side of their Streaming Mode API, allowing you to simulate how calls would be handled in a production environment.

## Components

### Server (`server.py`)

- Handles WebRTC connections for audio capture
- Implements the AudioCodes WebSocket server protocol
- Processes and saves audio recordings
- Simulates voice recognition and responses

### Bridge Client (`bridge_client.py`)

- Connects to the WebSocket server, simulating AudioCodes VoiceAI Connect
- Sends audio data to the bot using the AudioCodes protocol
- Handles conversation flow management

### Web Test Interface (`/test-audiocodes`)

- A browser-based tool for testing the AudioCodes WebSocket protocol
- Allows manual sending of protocol messages
- Displays received responses

## Installation

1. Install the required dependencies:

```bash
pip install -r requirements.txt
```

2. You may need additional system-level dependencies for PyAudio and av:

**Ubuntu/Debian**:
```bash
sudo apt-get install portaudio19-dev python3-pyaudio ffmpeg libavdevice-dev
```

**Windows**:
```bash
# PyAudio wheels can be installed directly from pip on Windows
# For av, you may need to install FFmpeg
```

**macOS**:
```bash
brew install portaudio ffmpeg
```

## Running the Server

Start the server with:

```bash
python server.py
```

This runs both the WebRTC server and the AudioCodes WebSocket server on port 8000.

## Testing the Integration

### Using the Web Interface

1. Navigate to `http://localhost:8000/test-audiocodes` in your browser
2. Click "Connect WebSocket"
3. Follow the protocol flow: Initiate Session → Start Stream → Send Chunks → Stop Stream → End Session

### Using the Bridge Client

The bridge client simulates AudioCodes VoiceAI Connect connecting to your bot. Run it with:

```bash
python bridge_client.py
```

This will:
1. Connect to the WebSocket endpoint
2. Initiate a session
3. Stream audio (from a sample file or generated silence)
4. Process responses
5. End the session

## Protocol Flow

The AudioCodes Bot API follows this sequence:

1. **Session Initiation**
   - AudioCodes sends `session.initiate`
   - Bot responds with `session.accepted`

2. **Audio Streaming**
   - AudioCodes sends `userStream.start`
   - Bot responds with `userStream.started`
   - AudioCodes sends multiple `userStream.chunk` messages with base64-encoded audio
   - Bot optionally sends `userStream.speech.hypothesis` during streaming
   - AudioCodes sends `userStream.stop`
   - Bot responds with `userStream.stopped`
   - Bot sends `userStream.speech.recognition` with final results

3. **Bot Response**
   - Bot sends `playStream.start`
   - Bot sends one or more `playStream.chunk` messages with base64-encoded audio
   - Bot sends `playStream.stop`

4. **Session End**
   - AudioCodes or bot sends `session.end`
   - Connection is closed

## Extending the POC

To create a production-ready implementation:

1. **Add Speech Recognition**: Connect to a speech-to-text service like Google STT, Azure Cognitive Services, or Whisper
2. **Add Text-to-Speech**: Generate audio responses from text using a TTS service
3. **Add Conversation Logic**: Integrate an LLM or agent framework to handle the conversation flow
4. **Add Authentication**: Implement secure token validation
5. **Add Monitoring and Logging**: Track conversation success rates and audio quality

## Resources

- [AudioCodes Bot API Documentation](https://techdocs.audiocodes.com/voice-ai-connect/Content/Bot-API/ac-bot-api-streaming.htm)
- [FastAPI WebSocket Documentation](https://fastapi.tiangolo.com/advanced/websockets/)
- [aiortc Documentation](https://aiortc.readthedocs.io/)
