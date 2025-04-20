import asyncio
import os
import wave
import pytest
import numpy as np
import fractions
import queue
from unittest.mock import patch, MagicMock, AsyncMock
from aiortc import RTCPeerConnection, RTCSessionDescription
from aiortc.mediastreams import MediaStreamError

# Import the client classes for testing
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from client import AudioStreamPlayer, MicrophoneStreamTrack


class TestAudioStreamPlayer:
    """Tests for the AudioStreamPlayer class"""
    
    @pytest.fixture
    def mock_track(self):
        """Create a mock audio track"""
        track = MagicMock()
        # Create a mock frame that will be returned by the track
        mock_frame = MagicMock()
        # Configure the mock to return audio data when to_ndarray is called
        mock_frame.to_ndarray.return_value = np.zeros(1024, dtype=np.float32)
        
        # Configure the recv method to return the mock frame when awaited
        async def mock_recv():
            return mock_frame
            
        track.recv = mock_recv
        return track
    
    @pytest.fixture
    def audio_player(self, mock_track):
        """Create an AudioStreamPlayer instance for testing"""
        player = AudioStreamPlayer(mock_track, buffer_size=1024)
        # Disable recording for basic tests
        player.should_record = False
        return player
    
    @pytest.mark.asyncio
    async def test_start_and_stop(self, audio_player, mock_track):
        """Test starting and stopping the audio player"""
        # Mock PyAudio
        with patch('pyaudio.PyAudio') as mock_pyaudio:
            # Mock the stream
            mock_stream = MagicMock()
            mock_pyaudio.return_value.open.return_value = mock_stream
            
            # Start the player
            await audio_player.start()
            
            # Check that PyAudio was initialized
            mock_pyaudio.assert_called_once()
            
            # Check that open was called with correct parameters
            mock_pyaudio.return_value.open.assert_called_once()
            call_args = mock_pyaudio.return_value.open.call_args[1]
            assert call_args['format'] == 8  # pyaudio.paInt16 is actually 8 in the implementation
            assert call_args['channels'] == 1
            assert call_args['rate'] == 48000
            assert call_args['output'] == True
            assert call_args['frames_per_buffer'] == 1024
            
            # Check that stream was started
            mock_stream.start_stream.assert_called_once()
            
            # Stop the player right away to avoid the receive_frames coroutine
            await audio_player.stop()
            
            # Check that stream was stopped and closed
            mock_stream.stop_stream.assert_called_once()
            mock_stream.close.assert_called_once()
            
            # Check that PyAudio was terminated
            mock_pyaudio.return_value.terminate.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_receive_frames(self, audio_player, mock_track):
        """Test receiving frames from the track"""
        # Create a mock audio frame
        mock_frame = MagicMock()
        mock_audio_data = np.zeros(1024, dtype=np.float32)
        mock_frame.to_ndarray.return_value = mock_audio_data
        
        # Update the mock_track recv to return our specific frame
        async def mock_recv():
            return mock_frame
            
        mock_track.recv = mock_recv
        
        # Mock PyAudio
        with patch('pyaudio.PyAudio') as mock_pyaudio:
            # Mock the stream
            mock_stream = MagicMock()
            mock_pyaudio.return_value.open.return_value = mock_stream
            
            # Start the player
            await audio_player.start()
            
            # Let the receive_frames coroutine run for a bit
            await asyncio.sleep(0.1)
            
            # Stop the player
            await audio_player.stop()
    
    @pytest.mark.asyncio
    async def test_recording(self, mock_track):
        """Test recording functionality"""
        # Create a player with recording enabled
        player = AudioStreamPlayer(mock_track, buffer_size=1024)
        player.should_record = True
        
        # Create a temporary recording path
        test_recording_path = "client_recordings/test_recording.wav"
        player.recording_filename = test_recording_path
        
        # Create a mock audio frame with known data
        mock_frame = MagicMock()
        test_audio = np.sin(np.linspace(0, 2*np.pi, 1024)) * 0.5  # Sine wave at half amplitude
        mock_frame.to_ndarray.return_value = test_audio
        
        # Update the mock_track recv to return our specific frame
        async def mock_recv():
            return mock_frame
            
        mock_track.recv = mock_recv
        
        try:
            # Mock wave module
            with patch('wave.open') as mock_wave_open:
                # Mock the wave file
                mock_wave_file = MagicMock()
                mock_wave_open.return_value = mock_wave_file
                
                # Mock PyAudio
                with patch('pyaudio.PyAudio') as mock_pyaudio:
                    # Mock the stream
                    mock_stream = MagicMock()
                    mock_pyaudio.return_value.open.return_value = mock_stream
                    
                    # Start the player
                    await player.start()
                    
                    # Let the receive_frames coroutine run for a bit
                    await asyncio.sleep(0.1)
                    
                    # Check that wave file was opened
                    mock_wave_open.assert_called_once_with(test_recording_path, "wb")
                    
                    # Check that wave file parameters were set
                    mock_wave_file.setnchannels.assert_called_once_with(1)
                    mock_wave_file.setsampwidth.assert_called_once_with(2)
                    mock_wave_file.setframerate.assert_called_once_with(48000)
                    
                    # Stop the player
                    await player.stop()
                    
                    # Check that wave file was closed and data was written
                    mock_wave_file.writeframes.assert_called()
                    mock_wave_file.close.assert_called_once()
        finally:
            # Clean up the test file if it was created
            if os.path.exists(test_recording_path):
                os.remove(test_recording_path)


class TestMicrophoneStreamTrack:
    """Tests for the MicrophoneStreamTrack class"""
    
    @pytest.mark.asyncio
    async def test_start_and_stop(self):
        """Test starting and stopping the microphone track"""
        
        # Mock PyAudio
        with patch('pyaudio.PyAudio') as mock_pyaudio:
            # Mock the stream
            mock_stream = MagicMock()
            mock_pyaudio.return_value.open.return_value = mock_stream
            
            # Create a microphone track
            mic_track = MicrophoneStreamTrack()
            
            # Start the track
            await mic_track.start()
            
            # Check that PyAudio was initialized
            mock_pyaudio.assert_called_once()
            
            # Check that open was called with correct parameters
            mock_pyaudio.return_value.open.assert_called_once()
            call_args = mock_pyaudio.return_value.open.call_args[1]
            assert call_args['format'] == 8  # pyaudio.paInt16
            assert call_args['channels'] == 1
            assert call_args['rate'] == 48000
            assert call_args['input'] == True
            
            # Check that stream was started
            mock_stream.start_stream.assert_called_once()
            
            # Stop the track
            await mic_track.stop()
            
            # Check that stream was stopped and closed
            mock_stream.stop_stream.assert_called_once()
            mock_stream.close.assert_called_once()
            
            # Check that PyAudio was terminated
            mock_pyaudio.return_value.terminate.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_recv(self):
        """Test receiving audio data from the microphone"""
        
        # Create test audio data
        test_audio_data = np.sin(np.linspace(0, 2*np.pi, 960)) * 32767
        test_audio_bytes = test_audio_data.astype(np.int16).tobytes()
        
        # Mock PyAudio
        with patch('pyaudio.PyAudio') as mock_pyaudio:
            # Mock the stream
            mock_stream = MagicMock()
            mock_pyaudio.return_value.open.return_value = mock_stream
            
            # Create a microphone track
            mic_track = MicrophoneStreamTrack()
            
            # Start the track
            await mic_track.start()
            
            try:
                # Put test data in the thread queue
                mic_track.thread_queue.put(test_audio_bytes)
                
                # Mock the AudioFrame creation
                with patch('av.AudioFrame') as mock_audio_frame:
                    # Configure the mock frame
                    mock_frame = MagicMock()
                    mock_audio_frame.return_value = mock_frame
                    mock_frame.planes = [MagicMock()]
                    
                    # Call recv() to get a frame
                    frame = await mic_track.recv()
                    
                    # Check that AudioFrame was created with correct parameters
                    mock_audio_frame.assert_called_once()
                    call_args = mock_audio_frame.call_args[1]
                    assert call_args['format'] == 's16'
                    assert call_args['layout'] == 'mono'
                    assert call_args['samples'] == len(test_audio_data)
                    
                    # Check that frame parameters were set
                    assert mock_frame.sample_rate == 48000
                    
                    # Check that audio data was copied to the frame
                    mock_frame.planes[0].update.assert_called_once_with(test_audio_bytes)
                    
                    assert frame == mock_frame
            finally:
                # Stop the track
                await mic_track.stop()
    
    @pytest.mark.asyncio
    async def test_inactive_connection(self):
        """Test behavior when connection is marked as inactive"""
        
        # Mock PyAudio
        with patch('pyaudio.PyAudio') as mock_pyaudio:
            # Mock the stream
            mock_stream = MagicMock()
            mock_pyaudio.return_value.open.return_value = mock_stream
            
            # Create a microphone track
            mic_track = MicrophoneStreamTrack()
            
            # Start the track
            await mic_track.start()
            
            try:
                # Mark connection as inactive
                mic_track.set_connection_inactive()
                
                # Check that connection_active is False
                assert mic_track.connection_active == False
                
                # Try to call recv() - should raise MediaStreamError
                with pytest.raises(MediaStreamError):
                    await mic_track.recv()
            finally:
                # Stop the track
                await mic_track.stop()


@pytest.mark.asyncio
async def test_run_test_client():
    """Test the main client function"""
    # Mock the necessary components
    with patch('client.RTCPeerConnection') as mock_pc_class:
        # Configure the mock peer connection
        mock_pc = MagicMock()
        mock_pc_class.return_value = mock_pc
        
        # Mock connection state
        mock_pc.connectionState = "connected"
        
        # Mock the data channel
        mock_dc = MagicMock()
        mock_pc.createDataChannel.return_value = mock_dc
        
        # Mock the offer creation
        mock_pc.createOffer = AsyncMock()
        mock_pc.setLocalDescription = AsyncMock()
        mock_pc.setRemoteDescription = AsyncMock()
        # Add AsyncMock for close method
        mock_pc.close = AsyncMock()
        
        # Mock localDescription
        mock_pc.localDescription = MagicMock()
        mock_pc.localDescription.sdp = "mock_offer_sdp"
        mock_pc.localDescription.type = "offer"
        
        # Mock aiohttp ClientSession
        with patch('aiohttp.ClientSession') as mock_session_class:
            # Create mock implementations for context managers
            class AsyncContextManagerMock:
                def __init__(self, return_value):
                    self.return_value = return_value
                
                async def __aenter__(self):
                    return self.return_value
                
                async def __aexit__(self, exc_type, exc_val, exc_tb):
                    pass
            
            # Configure the mock response
            mock_response = AsyncMock()
            mock_response.status = 200
            mock_response.json = AsyncMock(return_value={"sdp": "mock_answer_sdp", "type": "answer"})
            mock_response.text = AsyncMock(return_value="")
            
            # Configure the mock session
            mock_session = AsyncMock()
            mock_session_post_cm = AsyncContextManagerMock(mock_response)
            mock_session.post = AsyncMock(return_value=mock_session_post_cm)
            
            # Configure the session class
            mock_session_class.return_value = AsyncContextManagerMock(mock_session)
            
            # Mock MicrophoneStreamTrack
            with patch('client.MicrophoneStreamTrack') as mock_mic_class:
                # Configure the mock microphone track
                mock_mic = MagicMock()
                mock_mic_class.return_value = mock_mic
                mock_mic.start = AsyncMock()
                mock_mic.stop = AsyncMock()
                
                # Mock AudioStreamPlayer
                with patch('client.AudioStreamPlayer') as mock_player_class:
                    # Configure the mock player
                    mock_player = MagicMock()
                    mock_player_class.return_value = mock_player
                    mock_player.start = AsyncMock()
                    mock_player.stop = AsyncMock()
                    
                    # Mock asyncio.wait_for to return immediately instead of waiting
                    with patch('asyncio.wait_for', AsyncMock(side_effect=asyncio.TimeoutError)):
                        # Run the test client
                        from client import run_test_client
                        await run_test_client("http://test-server:8000")
                        
                        # Verify the expected calls were made
                        mock_pc_class.assert_called_once()
                        mock_pc.createDataChannel.assert_called_once_with("test-client-data")
                        mock_pc.addTransceiver.assert_called_once()
                        mock_mic_class.assert_called_once()
                        mock_mic.start.assert_called_once()
                        mock_pc.addTrack.assert_called_once()
                        mock_pc.createOffer.assert_called_once()
                        mock_pc.setLocalDescription.assert_called_once()
                        mock_session.post.assert_called_once()
                        mock_pc.setRemoteDescription.assert_called_once()
                        # Verification that cleanup occurred
                        mock_mic.stop.assert_called_once()
                        mock_pc.close.assert_called_once() 