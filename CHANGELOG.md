# Changelog

All notable changes to the Real-Time Voice Agent project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [Unreleased]

### Added
- OpenAI Realtime API integration
  - Added `RealtimeAudioClient` class for low-latency audio streaming with OpenAI
  - Implemented robust connection management with auto-reconnection
  - Added heartbeat monitoring to ensure connection health
  - Added proper error handling for API and connection issues

- Bridge module connecting AudioCodes WebSocket protocol with OpenAI Realtime API
  - Created `AudiocodesRealtimeBridge` class to manage streaming in both directions
  - Implemented conversation-specific client management
  - Added proper cleanup of resources when sessions end

- OpenAI message schemas using Pydantic
  - Added type-safe models for all Realtime API message types
  - Implemented proper validation for incoming messages
  - Added support for transcript, function calling, and error messages

- Enhanced configuration system
  - Added environment variable loading with dotenv
  - Created example configuration file with documentation
  - Added configurable logging levels and server settings

- Unit tests for OpenAI Realtime client
  - Added test coverage for connection management
  - Implemented tests for audio streaming
  - Added tests for error handling and reconnection logic

### Changed
- Improved JSON serialization in WebSocket communications
  - Replaced string manipulation with proper json.dumps()
  - Added consistent error handling for JSON parsing

- Enhanced logging system
  - Added rotating file logs
  - Implemented consistent log format
  - Added configurable log levels

- Updated FastAPI application
  - Added proper OpenAPI documentation
  - Enhanced health check endpoint
  - Added root information endpoint

## [1.2.0] - 2023-09-05

### Added
- WebSocket client implementation with Pydantic models for AudioCodes integration
  - Added `AudioCodesClient` class in `app/services/websocket_client.py`
  - Implemented session management, audio streaming, and activity handling
  - Added proper error handling and connection lifecycle management
  - Included support for all AudioCodes message types

- Enhanced validation for message schemas
  - Added base64 validation for audio chunks
  - Added media format validation against supported formats
  - Added phone number pattern validation
  - Added UUID pattern validation for conversation IDs
  - Enhanced DTMF input validation for digits
  - Added validators for empty collections and required fields

- Comprehensive unit tests for message validation
  - Added test cases for all message types
  - Included tests for both valid and invalid scenarios
  - Tested base64 encoding validation
  - Tested format constraints
  - Tested required fields and type constraints

### Changed
- Updated handler files to use Pydantic models instead of raw dictionaries
  - Refactored `session_handlers.py` to use SessionInitiateMessage, etc.
  - Refactored `stream_handlers.py` to use UserStreamChunkMessage, etc.
  - Refactored `activity_handlers.py` to use ActivitiesMessage, ActivityEvent
  - Updated WebSocket manager to handle Pydantic models

- Improved error handling in all handler functions
  - Added ValidationError catching
  - Added graceful fallbacks for invalid messages
  - Enhanced logging of validation failures

### Fixed
- Improved message serialization using model.json() instead of manual JSON formatting
- Fixed potential type issues with message handlers by adding proper Union return types
- Added better validation for DTMF values to prevent invalid input

## [1.1.0] - 2023-08-15

### Added
- Initial implementation of AudioCodes VoiceAI Connect integration
- Basic WebSocket handlers for session management
- Audio streaming support
- Activity and event processing 