"""
Configuration module for the real-time voice agent application.

This module provides centralized configuration management for the entire application,
including constants, logging setup, and environment-based configuration.

Key components:
- constants: Defines application-wide constants used across modules, including
  message types, audio formats, and default model settings.
- logging_config: Provides a consistent logging infrastructure with support for
  console and file-based logging with rotation capabilities.

The configuration module serves as the foundation for consistent behavior
across the application, enabling easy maintenance and configuration changes.

Usage examples:
```python
# Import and use constants
from app.config.constants import LOGGER_NAME, DEFAULT_REALTIME_MODEL
from app.config.constants import MESSAGE_TYPE_USER_STREAM_CHUNK

# Set up logging for your module
from app.config.logging_config import configure_logging
logger = configure_logging()
logger.info("Application started")

# Access audio format constants
from app.config.constants import AUDIO_FORMAT_RAW_LPCM16
audio_format = AUDIO_FORMAT_RAW_LPCM16
```
"""

# Config module initialization 