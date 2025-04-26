# AudioCodes Bot API Implementation

This project implements a WebSocket-based server and client that demonstrate the AudioCodes Bot API for voice bots.

## Components

- `ac_server.py`: FastAPI WebSocket server that handles various message types from the AudioCodes Bot API
- `ac_client.py`: Client implementation to test and demonstrate the server functionality

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
python ac_server.py
```

The server will start on `http://localhost:8000`. The WebSocket endpoint is available at `ws://localhost:8000/ws`.

## Running the Client

Once the server is running, you can test it with the client:

```bash
python ac_client.py
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

This implementation follows the AudioCodes Bot API specification for real-time voice agents. For more details, refer to the official AudioCodes documentation. 