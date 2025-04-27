# Real-Time Voice Agent Documentation

This document provides an overview of the Real-Time Voice Agent system - an AudioCodes to OpenAI Realtime API Bridge.

## System Overview

The Real-Time Voice Agent provides a complete solution for integrating AudioCodes VoiceAI Connect Enterprise platform with OpenAI's Realtime API to create real-time, speech-to-speech voice agents that can handle phone calls with natural conversation.

The application acts as a bridge between the AudioCodes WebSocket protocol and OpenAI's Realtime API, enabling bidirectional streaming of audio for seamless conversations.

## Architecture Overview

- FastAPI server exposing WebSocket endpoints for AudioCodes connectivity
- OpenAI Realtime API integration for AI model inference
- Bidirectional audio streaming with protocol conversion
- Stateful conversation management

## Key Modules

### Core Application (`app/__init__.py`)

The main application package provides the foundation for integrating AudioCodes VoiceAI Connect Enterprise platform with OpenAI's Realtime API.

**Key Components:**
- FastAPI server exposing WebSocket endpoints
- Bidirectional audio streaming with protocol conversion
- Stateful conversation management

### Bot Module (`app/bot/__init__.py`)

Core components for integrating OpenAI Realtime API with AudioCodes VoiceAI Connect.

**Key Components:**
- `RealtimeAudioClient`: Client for connecting to OpenAI's Realtime API over WebSockets to stream audio bidirectionally with features like auto-reconnection and heartbeats.
- `AudiocodesRealtimeBridge`: Bidirectional bridge that handles protocol conversion between AudioCodes VoiceAI Connect platform and OpenAI's Realtime API.

### Configuration Module (`app/config/__init__.py`)

Centralized configuration management for the entire application.

**Key Components:**
- `constants`: Application-wide constants including message types, audio formats, and default model settings.
- `logging_config`: Consistent logging infrastructure with support for console and file-based logging.

### Handlers Module (`app/handlers/__init__.py`)

WebSocket message handlers for AudioCodes communication.

**Key Components:**
- `session_handlers`: Manages WebSocket session lifecycle (initiate, resume, end).
- `stream_handlers`: Processes audio streaming, handling audio chunks and stream control messages.
- `activity_handlers`: Handles call events, DTMF inputs, and hangup requests.

### Models Module (`app/models/__init__.py`)

Data structures and state management for the application.

**Key Components:**
- `message_schemas`: Pydantic models for AudioCodes Bot API WebSocket protocol.
- `openai_schemas`: Type-safe models for OpenAI Realtime API message structures.
- `conversation`: State management for active voice conversations.

### Services Module (`app/services/__init__.py`)

External API integrations and client implementations.

**Key Components:**
- `websocket_client`: Client implementation for connecting to AudioCodes VoiceAI Connect Enterprise platform via WebSocket.

### WebSocket Manager (`app/websocket_manager.py`)

Central handler for AudioCodes WebSocket connections and message routing.

## Application Entry Point

The application is a FastAPI server defined in `app/main.py`. It provides the following endpoints:

- `/ws`: WebSocket endpoint for AudioCodes VoiceAI Connect integration
- `/health`: Health check endpoint for monitoring system status
- `/`: Root endpoint that provides basic API information

The application loads environment variables from a `.env` file if it exists and configures logging through the configuration module.

## Getting Started

1. Set up environment variables:
   - `OPENAI_API_KEY`: Your OpenAI API key
   - `PORT`: Port to run the server on (default 8000)
   - `HOST`: Host to bind the server to (default 0.0.0.0)
   - `LOG_LEVEL`: Logging level (default INFO)

2. Start the server:
   ```powershell
   # Using the run.py script
   python run.py
   
   # Or directly with the module
   python -m app.main
   ```

3. Configure AudioCodes VoiceAI Connect to point to your server:
   - Webhook URL: http://your-server:8000/ws
   - Configure the appropriate call flow in AudioCodes

## Data Flow

1. Incoming call reaches AudioCodes VoiceAI Connect platform
2. AudioCodes establishes WebSocket connection with this application
3. Application initiates OpenAI Realtime API session
4. Bidirectional audio streaming begins:
   - Caller audio → AudioCodes → This application → OpenAI
   - OpenAI responses → This application → AudioCodes → Caller
5. Call ends, sessions are terminated

## System Requirements

- Python 3.8+
- FastAPI and Uvicorn
- AudioCodes VoiceAI Connect Enterprise access
- OpenAI API key with access to Realtime API
