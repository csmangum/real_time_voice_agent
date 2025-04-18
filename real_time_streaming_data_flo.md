# Real-Time Audio Streaming: Data Flow Documentation

## Overview

This document explains how audio data flows from a user's microphone to the server in our WebRTC-based real-time streaming system.

## Complete Data Flow

### 1. Audio Capture (Client Side)
- **Microphone Access**: The system uses PyAudio to access the local microphone
- **Sampling**: Audio is continuously sampled at 48kHz (by default) in 16-bit format
- **Buffer Creation**: Raw audio data is collected in frames of 960 samples
- **Queue Management**: Captured frames are added to an async queue for processing

### 2. WebRTC Processing (Client Side)
- **Media Track Creation**: Audio is wrapped in a `PyAudioStreamTrack` that implements the WebRTC MediaStreamTrack interface
- **Packetization**: The `recv()` method converts raw audio data to WebRTC-compatible frames
- **Encoding**: Audio is automatically encoded (typically using Opus codec) by the WebRTC stack
- **Encryption**: DTLS-SRTP encrypts the media for secure transmission

### 3. Connection Establishment
- **Signaling**: 
  - Client creates an "offer" with its capabilities
  - Server responds with an "answer"
  - This exchange uses HTTPS via the `/offer` endpoint
- **ICE Candidates**: 
  - Both sides discover network paths using STUN servers
  - Candidates are exchanged via the `/ice-candidate` endpoint
  - The best connection path is selected

### 4. Network Transport
- **RTP Protocol**: Audio packets are transmitted using RTP (Real-time Transport Protocol)
- **NAT Traversal**: ICE, STUN, and potentially TURN servers help establish direct connections
- **Packet Delivery**: Small audio chunks are continuously sent with timing information
- **Latency Handling**: Packets are prioritized for minimal delay rather than guaranteed delivery

### 5. Server-Side Processing
- **Packet Reception**: The server receives encrypted RTP packets
- **Decryption**: DTLS-SRTP decrypts the audio data
- **Decoding**: The audio is decoded from the transmission format (e.g., Opus)
- **Frame Processing**: `AudioTrackProcessor` processes each received frame
- **Format Detection**: The server analyzes and adapts to the incoming audio format
- **Audio Extraction**: Audio data is extracted using the appropriate method based on the frame type

### 6. Storage and Handling (Server Side)
- **In-Memory Buffer**: Processed audio frames are stored in memory
- **Recording**: The audio is saved to disk in WAV format
- **Format Preservation**: The detected format parameters (rate, channels, bit depth) are maintained
- **Cleanup**: Resources are properly released when connections end

## Key Technologies

- **WebRTC**: The overall framework for real-time communication
- **RTP/SRTP**: Protocols for transmitting real-time media packets
- **ICE/STUN/TURN**: NAT traversal technologies for establishing peer connections
- **PyAudio**: Library for accessing audio hardware
- **aiortc**: Python implementation of WebRTC
- **asyncio**: Asynchronous programming framework for handling concurrent operations

## Sequence Diagram

```mermaid
sequenceDiagram
    participant Client
    participant STUN as STUN Server
    participant Server

    Note over Client: Access microphone
    Note over Client: Capture audio frames

    Client->>Server: HTTP POST /offer
    Note right of Client: SDP with media capabilities
    
    Server->>Server: Create peer connection
    Server->>Server: Generate client ID
    Server->>Server: Initialize recorder
    
    Server-->>Client: HTTP Response with answer
    Note left of Server: SDP answer + client ID
    
    Client->>STUN: Discover network path
    STUN-->>Client: ICE candidates
    Server->>STUN: Discover network path
    STUN-->>Server: ICE candidates
    
    Client->>Server: POST /ice-candidate
    Note right of Client: Send ICE candidates
    Server-->>Client: Accept candidates
    
    Note over Client,Server: WebRTC connection established
    
    loop Audio streaming
        Client->>Server: RTP packets (encrypted audio)
        Note right of Client: ~20ms chunks, Opus encoded
        Server->>Server: Process audio frame
        Server->>Server: Save to buffer
        Server->>Server: Record to disk
    end
    
    Note over Client: User ends session
    Client->>Server: Close connection
    Server->>Server: Save recording
    Server->>Server: Cleanup resources
```

## Connection Maintenance

- **Heartbeats**: WebRTC connections send periodic checks to ensure the link is active
- **Reconnection**: Temporary disconnections trigger reconnection attempts
- **Inactivity Timeouts**: Connections are closed after 30 seconds of inactivity
- **Cleanup**: Resources are properly released when connections end

This comprehensive flow enables low-latency, secure audio streaming from the client microphone to server processing with minimal delay and robust error handling. 

## Usage Guide

### Starting the Server
```bash
python server.py
```
This will:
- Start a FastAPI server on port 8000
- Create a web interface accessible at http://localhost:8000
- Create a "recordings" directory if it doesn't exist

### Running the Client
```bash
python client.py [options]
```

#### Client Options
- `--server URL`: Server URL (default: http://localhost:8000)
- `--duration SECONDS`: Maximum recording duration (default: 60 seconds)
- `--no-save-local`: Disable client-side audio recording
- `--sample-rate RATE`: Audio sample rate (default: 16000 Hz)

#### Example Commands
```bash
# Connect to local server with default settings
python client.py

# Connect to remote server with longer recording time
python client.py --server http://example.com:8000 --duration 120

# Use higher sample rate and don't save locally
python client.py --sample-rate 44100 --no-save-local
```

### Usage Flow
1. Start the server first
2. Run the client with desired options
3. Press Enter in the client terminal to start streaming
4. Audio will be captured from your microphone and sent to the server
5. The client will automatically stop after the specified duration
6. Or press Ctrl+C to stop earlier
7. Recordings are saved in the "recordings" directory on both client and server

### Recordings Format
- All recordings are saved as WAV files
- The server creates two recordings:
  - A MediaRecorder version (recordings/audio_*.wav)
  - A higher-quality version from raw frames (recordings/main_*.wav)
- The client saves a local recording if not disabled (recordings/client_audio_*.wav) 