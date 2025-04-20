# WebRTC Client Explanation

## Overview

The `client.py` implements a WebRTC client that establishes bidirectional audio streaming with the server. The client:

1. Captures audio from the local microphone and sends it to the server
2. Receives and plays audio streams from the server
3. Records received audio to WAV files for later analysis
4. Implements jitter buffering and audio normalization for improved quality

## Bidirectional Audio Streaming

### Client → Server Audio Flow

1. The `MicrophoneStreamTrack` class captures audio from the local microphone
2. Audio is captured at 48kHz with 16-bit samples (standard for WebRTC)
3. Audio frames are formatted and queued for transmission
4. The WebRTC connection sends audio frames to the server
5. Connection state is monitored to stop sending when connection is lost

### Server → Client Audio Flow

1. The client receives audio from the server through a WebRTC audio track
2. The `AudioStreamPlayer` class processes and plays incoming audio
3. Audio is buffered to handle network jitter (variable latency)
4. Normalization and gain adjustments improve audio quality
5. Incoming audio is recorded to WAV files in the `client_recordings` directory

## Key Components

### Audio Capture and Playback

- **MicrophoneStreamTrack**: Custom AudioStreamTrack that captures microphone input
- **AudioStreamPlayer**: Handles playback and recording of received audio
- **PyAudio**: Used for low-level audio I/O with the system's audio devices
- **Queue Management**: Both standard Python queues and asyncio queues for thread-safe audio data handling

### Audio Processing

- **Buffering**: Implements prebuffering and jitter compensation
- **Normalization**: Adjusts audio levels for consistent volume
- **Sample Rate Conversion**: Ensures 48kHz sample rate compatible with WebRTC
- **Format Conversion**: Handles conversions between NumPy arrays and raw PCM data

### WebRTC Connection

- **RTCPeerConnection**: Manages the WebRTC connection with the server
- **RTCSessionDescription**: Handles SDP offer/answer exchange
- **ICE Candidate Handling**: Logs ICE candidates for connection negotiation
- **Connection State Monitoring**: Tracks connection state changes and performs cleanup

## Error Handling and Resilience

- **Graceful Shutdown**: Properly releases audio resources when stopping
- **Connection Loss Detection**: Detects disconnections and stops audio transmission
- **Exception Handling**: Comprehensive try/except blocks prevent crashes
- **Timeout Mechanism**: Automatic timeout after 60 seconds if no stop event

## Logging

- **Detailed Logging**: Logs connection events, audio processing, and errors
- **Log File Storage**: Saves logs to `logs` directory with timestamps
- **Console Output**: Provides user feedback in the terminal

## Performance Optimizations

- **Latency Reduction**: Small buffer sizes (2048 samples) to minimize playback delay
- **Adaptive Buffer Management**: Drops frames when buffer grows too large to maintain low latency
- **Efficient Data Transfer**: Uses separate thread and asyncio queues for non-blocking operations
- **Resource Management**: Proper cleanup of audio streams and connections 