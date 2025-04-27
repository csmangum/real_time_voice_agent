"""
Bot module for integrating OpenAI Realtime API with AudioCodes VoiceAI Connect.

This module provides components for real-time speech-to-speech conversations
by connecting the AudioCodes WebSocket protocol with OpenAI's Realtime API.
"""

from app.bot.realtime_api import RealtimeAudioClient
from app.bot.audiocodes_realtime_bridge import bridge, AudiocodesRealtimeBridge

__all__ = ["RealtimeAudioClient", "bridge", "AudiocodesRealtimeBridge"]
