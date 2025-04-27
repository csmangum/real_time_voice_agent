"""
Constants and configuration values used throughout the application.

This module defines constants that are used across different parts of the application,
providing a centralized location for configuration values and making it easier to 
maintain consistent naming throughout the codebase.
"""

# Logger name used throughout the application
LOGGER_NAME = "voice_agent"

# Default OpenAI model for Realtime API
DEFAULT_REALTIME_MODEL = "gpt-4o-realtime-preview-2024-12-17"

# Audio format constants
AUDIO_FORMAT_RAW_LPCM16 = "raw/lpcm16"
AUDIO_FORMAT_WAV_LPCM16 = "wav/lpcm16"
AUDIO_FORMAT_RAW_MULAW = "raw/mulaw"
AUDIO_FORMAT_WAV_MULAW = "wav/mulaw"

# Message type constants
MESSAGE_TYPE_SESSION_INITIATE = "session.initiate"
MESSAGE_TYPE_SESSION_RESUME = "session.resume"
MESSAGE_TYPE_SESSION_END = "session.end"
MESSAGE_TYPE_USER_STREAM_START = "userStream.start"
MESSAGE_TYPE_USER_STREAM_CHUNK = "userStream.chunk"
MESSAGE_TYPE_USER_STREAM_STOP = "userStream.stop"
MESSAGE_TYPE_PLAY_STREAM_START = "playStream.start"
MESSAGE_TYPE_PLAY_STREAM_CHUNK = "playStream.chunk"
MESSAGE_TYPE_PLAY_STREAM_STOP = "playStream.stop" 