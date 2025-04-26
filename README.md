# AudioCodes Bot API Implementation

This project implements a WebSocket-based server and client that demonstrate the AudioCodes Bot API for voice bots.

## Components

- `app/` - Directory containing the server implementation
  - `main.py` - FastAPI application with WebSocket endpoint
  - `websocket_manager.py` - Handles WebSocket connections and message routing
  - `handlers/` - Message type-specific handlers
  - `models/` - Data models for request/response validation
  - `services/` - Business logic services
  - `config/` - Application configuration
- `client.py` - Client implementation to test and demonstrate the server functionality
- `run.py` - Convenience script to start the server with hot-reload

## Features

- Session initiation and management
- Audio streaming (simulated)
- DTMF input handling
- Activity events processing
- Connectivity validation

## Requirements

Required Python packages are listed in `requirements.txt`. Install them with:

```bash
pip install -r requirements.txt
```

## Running the Server

Start the server with:

```bash
python run.py
```

The server will start on `http://localhost:8000`. The WebSocket endpoint is available at `ws://localhost:8000/ws`. A health check endpoint is available at `http://localhost:8000/health`.

## Running the Client

Once the server is running, you can test it with the client:

```bash
python client.py
```

The client will:
1. Initiate a session
2. Simulate a call start
3. Demonstrate audio streaming
4. Send DTMF digits
5. End the session

## Supported Message Types

### Server Handling
- `session.initiate` - Initial session creation
- `session.resume` - Session reconnection
- `userStream.start` - Start of audio streaming
- `userStream.chunk` - Audio data chunks
- `userStream.stop` - End of audio streaming
- `activities` - Various activity events
- `session.end` - End of conversation
- `connection.validate` - Connectivity validation

### Client Sending
- `session.initiate` - Request session creation
- `activities` (call start) - Simulate call initiation
- `userStream.start`, `userStream.chunk`, `userStream.stop` - Audio streaming sequence
- `activities` (DTMF) - Send button press signals
- `session.end` - End the conversation

## API Documentation

This implementation follows the AudioCodes Bot API specification for real-time voice agents. For more details, refer to the official [AudioCodes documentation](https://techdocs.audiocodes.com/voice-ai-connect/#Bot-API/ac-bot-api-mode-websocket.htm).

## Project Structure

```
.
├── app/                  # Server implementation
│   ├── config/           # Configuration files
│   ├── handlers/         # Message type handlers
│   ├── models/           # Data models
│   ├── services/         # Business logic
│   ├── __init__.py
│   ├── main.py           # Main FastAPI application
│   └── websocket_manager.py # WebSocket connection manager
├── tests/                # Test directory
├── static/               # Static assets
├── client.py             # Test client implementation
├── run.py                # Server startup script
├── requirements.txt      # Package dependencies
└── README.md             # This file
``` 