# WebRTC Server Explanation

## Overview

The `server.py` file implements a WebRTC server using FastAPI that enables bidirectional audio streaming between clients and the server. The server:

1. Receives audio from clients and records it to WAV files
2. Streams a sample audio file back to clients
3. Handles WebRTC connection setup, ICE candidates, and connection state changes
4. Logs all activities for debugging and tracking

## Bidirectional Audio Streaming

### Client → Server Audio Flow

1. When a client connects, the server creates a unique peer connection
2. The server sets up a track handler to capture incoming audio from the client
3. Incoming audio is recorded to a file in the `server_recordings` directory
4. The filename includes the unique connection ID and timestamp

### Server → Client Audio Flow

1. The server loads an audio file (`static/sample.wav`)
2. The audio is streamed through a MediaPlayer with loop=True (continuous playback)
3. The audio track is wrapped in a MediaRelay for consistent sharing
4. This audio track is added to the peer connection and sent to the client

## Key Components

### WebRTC Setup

- **RTCPeerConnection**: Creates WebRTC connections for each client
- **MediaRelay**: Enables sharing a single media source with multiple clients
- **MediaRecorder**: Records incoming audio streams to WAV files
- **MediaPlayer**: Plays the sample audio file to send to clients

### Connection Management

- Tracks active connections in the `peer_connections` dictionary
- Handles connection state changes and performs cleanup when connections end
- Properly releases resources (recorders, connections) when clients disconnect

### Error Handling

- Comprehensive try/except blocks to handle various failure scenarios
- Detailed logging for debugging purposes
- Proper HTTP exception responses for client-facing errors

## Configuration

- Audio Format: The server configures the outgoing audio with specific parameters:
  - Mono channel (1 channel)
  - 16-bit signed PCM format
  - 48kHz sample rate (standard for WebRTC)
  - 10ms packetization time
  - 4096 buffer size for stability
  - 1000ms jitter buffer

## Logging

- Logs are stored in the `logs` directory with timestamps
- Both console and file logging is configured
- Detailed debug-level logging for troubleshooting

## API Endpoint

- `/offer`: Handles WebRTC offer requests from clients, sets up the connection, and returns an answer to establish the WebRTC session 