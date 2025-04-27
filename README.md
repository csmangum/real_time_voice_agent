# Real-Time Voice Agent

A real-time voice agent that integrates AudioCodes VoiceAI Connect Enterprise with OpenAI Realtime API for speech-to-speech conversations.

## Overview

This application serves as a bridge between:
- **AudioCodes VoiceAI Connect Enterprise** - A platform for building voice bots over telephony systems
- **OpenAI Realtime API** - A low-latency multimodal API that enables speech-to-speech conversations

The integration allows phone callers to have natural conversations with an AI assistant powered by OpenAI's latest voice models.

## Features

- Real-time audio streaming in both directions
- WebSocket-based communication following the AudioCodes Bot API protocol
- Direct streaming of audio between AudioCodes and OpenAI without intermediate transcription
- Conversation state management throughout the call lifecycle

## Prerequisites

- Python 3.9+
- An AudioCodes VoiceAI Connect Enterprise account
- An OpenAI API key with access to Realtime API
- Network access to both AudioCodes and OpenAI APIs

## Installation

1. Clone the repository:
   ```powershell
   git clone https://github.com/yourusername/real-time-voice-agent.git
   cd real-time-voice-agent
   ```

2. Create a virtual environment:
   ```powershell
   python -m venv venv
   .\venv\Scripts\activate
   ```

3. Install dependencies:
   ```powershell
   pip install -r requirements.txt
   ```

4. Set your OpenAI API key:
   ```powershell
   $env:OPENAI_API_KEY="your-api-key-here"
   ```

## Usage

1. Start the server:
   ```powershell
   python -m app.main
   ```

2. Configure AudioCodes VoiceAI Connect Enterprise:
   - Set the bot type to "ac-api"
   - Set the botUrl to your server's WebSocket endpoint (e.g., `wss://your-server.com/ws`)
   - Set directSTT and directTTS to true

3. Make a test call to your AudioCodes phone number

## Configuration

The application can be configured using environment variables:

- `OPENAI_API_KEY` - Your OpenAI API key (required)
- `OPENAI_REALTIME_MODEL` - The model to use for real-time conversations (default: `gpt-4o-realtime-preview-2024-12-17`)
- `PORT` - The port to run the server on (default: 8000)

## Architecture

The application follows a modular architecture:

- `app/main.py` - FastAPI application entry point
- `app/bot/` - OpenAI Realtime API integration
- `app/handlers/` - AudioCodes WebSocket message handlers
- `app/models/` - Data models and conversation state management
- `app/config/` - Configuration and constants

## Documentation

For more detailed information about the system:

- [Documentation](DOC.md) - Comprehensive technical documentation including system overview, architecture details, and key modules
- [Changelog](CHANGELOG.md) - Complete history of changes and updates to the project

## Development

### Adding New Features

1. Implement new handlers in the appropriate modules
2. Register handlers in the WebSocketManager
3. Update model schemas if needed

### Running Tests

```powershell
pytest
```

## License

[MIT](LICENSE) 