import os
import time
import wave
import pyaudio
import asyncio

async def record_audio(duration=5, sample_rate=48000, channels=1, chunk=960):
    """Record audio for a specified duration and save it to a file."""
    print(f"Recording {duration} seconds of audio...")
    
    # Create recordings directory if it doesn't exist
    os.makedirs("recordings", exist_ok=True)
    timestamp = time.strftime("%Y%m%d-%H%M%S")
    output_file = f"recordings/test_recording_{timestamp}.wav"
    
    # Initialize PyAudio
    p = pyaudio.PyAudio()
    
    # Open audio stream
    stream = p.open(
        format=pyaudio.paInt16,
        channels=channels,
        rate=sample_rate,
        input=True,
        frames_per_buffer=chunk,
    )
    
    # Record audio
    frames = []
    total_bytes = 0
    start_time = time.time()
    
    # Print audio device info
    info = p.get_default_input_device_info()
    print(f"Default input device: {info['name']} (ID: {info['index']})")
    print(f"Device supports: {info['maxInputChannels']} channels, rates: {info.get('defaultSampleRate', 'unknown')}")
    
    # Wait for the specified duration
    try:
        while time.time() - start_time < duration:
            data = stream.read(chunk, exception_on_overflow=False)
            frames.append(data)
            total_bytes += len(data)
            
            elapsed = time.time() - start_time
            if len(frames) % 100 == 0:
                print(f"Recorded {elapsed:.1f}/{duration} seconds... ({total_bytes/1024:.1f} KB)")
            
            # Small sleep to allow other tasks to run
            await asyncio.sleep(0.001)
    except KeyboardInterrupt:
        print("Recording stopped early by user.")
    
    # Stop and close the stream
    stream.stop_stream()
    stream.close()
    p.terminate()
    
    # Save the recorded data as a WAV file
    with wave.open(output_file, 'wb') as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(2)  # 2 bytes for 'int16'
        wf.setframerate(sample_rate)
        wf.writeframes(b''.join(frames))
    
    file_size = os.path.getsize(output_file)
    print(f"Recording complete. Audio saved to {output_file} ({file_size/1024:.1f} KB)")
    
    # List files in recordings directory
    files = os.listdir("recordings")
    print(f"Recording directory contains {len(files)} files:")
    for file in files:
        file_path = os.path.join("recordings", file)
        file_size = os.path.getsize(file_path)
        print(f"- {file}: {file_size/1024:.1f} KB")
    
    return output_file

async def main():
    # Record 5 seconds of audio
    parser_duration = 5
    print("Starting audio recording test")
    output_file = await record_audio(parser_duration)
    print(f"Audio test completed successfully: {output_file}")

if __name__ == "__main__":
    asyncio.run(main()) 