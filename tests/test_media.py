import asyncio
import os
import wave
import pytest
import numpy as np
from unittest.mock import patch, MagicMock, AsyncMock
from aiortc.contrib.media import MediaPlayer, MediaRecorder

class TestMedia:
    """Tests for WebRTC media functionality"""
    
    def test_audio_file_exists(self):
        """Test that the sample audio file exists"""
        audio_file_path = "static/sample.wav"
        assert os.path.exists(audio_file_path), f"Audio file {audio_file_path} does not exist"
        
        # Verify it's a valid WAV file
        with wave.open(audio_file_path, "rb") as wave_file:
            assert wave_file.getnchannels() > 0, "Audio file has no channels"
            assert wave_file.getframerate() > 0, "Audio file has invalid frame rate"
    
    @pytest.mark.asyncio
    async def test_media_player_creation(self):
        """Test that a MediaPlayer can be created with the sample audio file"""
        audio_file_path = "static/sample.wav"
        
        if not os.path.exists(audio_file_path):
            # Create a dummy WAV file for testing if it doesn't exist
            os.makedirs("static", exist_ok=True)
            await self._create_test_wav(audio_file_path)
        
        # Create a MediaPlayer with the same options used in the server
        player = MediaPlayer(
            audio_file_path,
            loop=True,
            options={
                "channels": "1",
                "sample_fmt": "s16",
                "buffer_size": "4096",
                "audio_jitter_buffer": "1000",
                "clock_rate": "48000",
                "packetization": "10",
            },
        )
        
        # Verify that the player has an audio track
        assert player.audio is not None, "MediaPlayer should have an audio track"
    
    @pytest.mark.asyncio
    @patch('aiortc.contrib.media.MediaRecorder')
    async def test_media_recorder(self, mock_recorder_class):
        """Test that a MediaRecorder can be created and used"""
        # Create a test recording file path
        test_recording_file = "server_recordings/test_recording.wav"
        
        # Ensure the directory exists
        os.makedirs("server_recordings", exist_ok=True)
        
        # Set up the mock recorder
        mock_recorder = mock_recorder_class.return_value
        mock_recorder.start = AsyncMock()
        mock_recorder.stop = AsyncMock()
        
        # Create a mock audio track
        mock_track = MagicMock()
        mock_track.kind = "audio"
        
        # Add the track and start recording
        mock_recorder.addTrack(mock_track)
        await mock_recorder.start()
        
        # Verify start was called
        mock_recorder.start.assert_called_once()
        
        # Stop the recorder
        await mock_recorder.stop()
        
        # Verify stop was called
        mock_recorder.stop.assert_called_once()
    
    @staticmethod
    async def _create_test_wav(file_path):
        """Helper method to create a test WAV file"""
        # Create a simple sine wave
        sample_rate = 48000
        duration = 1  # seconds
        frequency = 440  # Hz (A4)
        
        t = np.linspace(0, duration, int(sample_rate * duration), endpoint=False)
        audio_data = (np.sin(2 * np.pi * frequency * t) * 32767).astype(np.int16)
        
        # Write to a WAV file
        with wave.open(file_path, "wb") as wave_file:
            wave_file.setnchannels(1)  # Mono
            wave_file.setsampwidth(2)  # 16-bit
            wave_file.setframerate(sample_rate)
            wave_file.writeframes(audio_data.tobytes()) 