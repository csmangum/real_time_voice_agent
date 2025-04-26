# Changelog

All notable changes to the Real-Time Voice Agent project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [Unreleased]

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