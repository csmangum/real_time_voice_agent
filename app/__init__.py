"""
Real-Time Voice Agent - AudioCodes to OpenAI Realtime API Bridge

This application provides a complete solution for integrating AudioCodes VoiceAI Connect
Enterprise platform with OpenAI's Realtime API to create real-time, speech-to-speech
voice agents that can handle phone calls with natural conversation.

The application acts as a bridge between the AudioCodes WebSocket protocol and OpenAI's
Realtime API, enabling bidirectional streaming of audio for seamless conversations.

Architecture Overview:
- FastAPI server exposing WebSocket endpoints for AudioCodes connectivity
- OpenAI Realtime API integration for AI model inference
- Bidirectional audio streaming with protocol conversion
- Stateful conversation management

Key Components:
- bot: Core components for OpenAI Realtime API integration and audio bridging
- config: Application-wide configuration, constants, and logging setup
- handlers: Message handlers for the AudioCodes WebSocket protocol
- models: Data structures and state management for conversations
- services: Client implementations for external API integrations
- websocket_manager: Central handler for WebSocket connections and message routing

Getting Started:
1. Set up environment variables:
   - OPENAI_API_KEY: Your OpenAI API key
   - PORT: Port to run the server on (default 8000)
   - HOST: Host to bind the server to (default 0.0.0.0)
   - LOG_LEVEL: Logging level (default INFO)

2. Start the server:
   ```bash
   python -m app.main
   ```

3. Configure AudioCodes VoiceAI Connect to point to your server:
   - Webhook URL: http://your-server:8000/ws
   - Configure the appropriate call flow in AudioCodes

This application handles the complete lifecycle of voice calls, from session
establishment to audio streaming and termination, enabling natural conversations
between callers and AI voice agents powered by OpenAI's models.
"""

# This file is intentionally left empty
# It makes the app directory a proper Python package 