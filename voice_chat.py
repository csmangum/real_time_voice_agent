import asyncio
import base64
import io
import os
import sys
import threading
import time
import tkinter as tk
import traceback
import wave
import queue
import numpy as np
from queue import Queue
from tkinter import ttk, scrolledtext

import pyaudio
import pyttsx3
import requests
import json
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Setup OpenAI API Key
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
if not OPENAI_API_KEY:
    raise ValueError("No OpenAI API key found. Please set the OPENAI_API_KEY environment variable.")

# Audio config
CHUNK = 1024
FORMAT = pyaudio.paInt16
CHANNELS = 1
RATE = 16000

# Default model
MODEL_NAME = "gpt-4o-mini"

# Voice activity detection parameters
SILENCE_THRESHOLD = 700  # Adjust based on your microphone and environment
SILENCE_FRAMES = 30  # Number of frames of silence needed to consider speaking stopped

class VoiceChatApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Voice Chat with AI")
        self.root.geometry("800x600")
        
        # Chat display
        self.chat_area = scrolledtext.ScrolledText(self.root, wrap=tk.WORD, height=20, width=80)
        self.chat_area.pack(padx=10, pady=10, fill=tk.BOTH, expand=True)
        
        # Status label
        self.status_label = ttk.Label(self.root, text="Ready to start")
        self.status_label.pack(pady=5)
        
        # Control buttons
        self.button_frame = ttk.Frame(self.root)
        self.button_frame.pack(pady=10)
        
        self.start_button = ttk.Button(self.button_frame, text="Start Conversation", command=self.start_chat)
        self.start_button.pack(side=tk.LEFT, padx=5)
        
        self.stop_button = ttk.Button(self.button_frame, text="Stop Conversation", command=self.stop_chat, state=tk.DISABLED)
        self.stop_button.pack(side=tk.LEFT, padx=5)
        
        # Model selection dropdown
        self.model_label = ttk.Label(self.root, text="Select Model:")
        self.model_label.pack(pady=5)
        
        self.model_var = tk.StringVar(value=MODEL_NAME)
        self.model_dropdown = ttk.Combobox(self.root, textvariable=self.model_var)
        self.model_dropdown['values'] = ('gpt-4o-mini', 'gpt-4o', 'gpt-3.5-turbo')
        self.model_dropdown.pack(pady=5)
        
        # Sensitivity slider
        self.sensitivity_label = ttk.Label(self.root, text="Mic Sensitivity:")
        self.sensitivity_label.pack(pady=5)
        
        self.sensitivity_var = tk.IntVar(value=SILENCE_THRESHOLD)
        self.sensitivity_slider = ttk.Scale(self.root, from_=200, to=2000, 
                                          orient=tk.HORIZONTAL, length=200,
                                          variable=self.sensitivity_var)
        self.sensitivity_slider.pack(pady=5)
        
        # Initialize TTS engine
        self.tts_engine = pyttsx3.init()
        
        # Audio processing
        self.running = False
        self.audio_buffer = []
        self.silence_counter = 0
        self.is_listening = True
        self.is_speaking = False
        
        # For streaming responses
        self.current_response = ""
        
        # Conversation history
        self.messages = [
            {"role": "system", "content": "You are a helpful, friendly, and concise voice assistant. Keep your responses relatively brief for a voice conversation."}
        ]
        
        # Audio interface
        self.p = pyaudio.PyAudio()
        self.stream = None
        
        # Audio processing queues
        self.audio_queue = queue.Queue()
        self.transcription_queue = queue.Queue()
        
        # Check OpenAI API access
        self.check_api_access()
        
    def check_api_access(self):
        """Check if the OpenAI API key is valid by making a simple request"""
        try:
            # Make a simple request to the Models endpoint
            response = requests.get(
                "https://api.openai.com/v1/models", 
                headers={"Authorization": f"Bearer {OPENAI_API_KEY}"}
            )
            
            if response.status_code == 200:
                models = response.json().get("data", [])
                model_ids = [model.get("id") for model in models]
                
                # Update dropdown with available models
                available_models = [m for m in self.model_dropdown['values'] if m in model_ids]
                if available_models:
                    self.model_dropdown['values'] = available_models
                    self.model_var.set(available_models[0])
                
                self.update_status("API key valid. Ready to start.")
            else:
                error_msg = response.json().get("error", {}).get("message", "Unknown error")
                self.update_status(f"API key error: {error_msg}")
        except Exception as e:
            self.update_status(f"API check error: {str(e)}")
        
    def start_chat(self):
        if not self.running:
            self.running = True
            self.start_button.config(state=tk.DISABLED)
            self.stop_button.config(state=tk.NORMAL)
            self.status_label.config(text="Starting conversation...")
            
            # Clear variables
            self.audio_buffer = []
            self.silence_counter = 0
            self.is_listening = True
            self.is_speaking = False
            
            # Add initial message to chat
            self.add_to_chat("System", "Conversation started. Speak now...")
            
            # Start audio processing in a separate thread
            self.audio_thread = threading.Thread(target=self.process_audio_stream)
            self.audio_thread.daemon = True
            self.audio_thread.start()
            
            # Start transcription processing in a separate thread
            self.transcription_thread = threading.Thread(target=self.process_transcriptions)
            self.transcription_thread.daemon = True
            self.transcription_thread.start()
    
    def stop_chat(self):
        if self.running:
            self.running = False
            self.start_button.config(state=tk.NORMAL)
            self.stop_button.config(state=tk.DISABLED)
            self.status_label.config(text="Conversation ended")
            self.add_to_chat("System", "Conversation ended.")
            
            # Close the audio stream if it's open
            if self.stream:
                self.stream.stop_stream()
                self.stream.close()
                self.stream = None
    
    def process_audio_stream(self):
        """Process audio stream continuously with voice activity detection"""
        try:
            # Set up audio stream
            self.stream = self.p.open(format=FORMAT,
                          channels=CHANNELS,
                          rate=RATE,
                          input=True,
                          frames_per_buffer=CHUNK,
                          stream_callback=self.audio_callback)
            
            self.stream.start_stream()
            self.update_status("Listening for speech...")
            
            # Keep the thread alive while the stream is active
            while self.running and self.stream.is_active():
                time.sleep(0.1)
                
        except Exception as e:
            self.update_status(f"Audio stream error: {str(e)}")
            traceback.print_exc()
        finally:
            if self.stream:
                self.stream.stop_stream()
                self.stream.close()
                self.stream = None
            self.p.terminate()
    
    def audio_callback(self, in_data, frame_count, time_info, status):
        """Callback for audio stream processing - runs in real-time with the audio hardware"""
        if self.running and self.is_listening and not self.is_speaking:
            try:
                # Convert audio data to numpy array for analysis
                audio_data = np.frombuffer(in_data, dtype=np.int16)
                audio_volume = np.abs(audio_data).mean()
                
                # Use the slider value for the threshold
                threshold = self.sensitivity_var.get()
                
                # Store the audio data
                self.audio_buffer.append(in_data)
                
                # Voice activity detection
                if audio_volume < threshold:
                    self.silence_counter += 1
                else:
                    self.silence_counter = 0
                
                # If we've detected enough silence and have some audio data
                if self.silence_counter >= SILENCE_FRAMES and len(self.audio_buffer) > 10:
                    # Create a copy of the buffer and clear it
                    buffer_copy = self.audio_buffer.copy()
                    self.audio_buffer = []
                    self.silence_counter = 0
                    
                    # Process this audio data in a separate thread
                    process_thread = threading.Thread(
                        target=lambda: self.process_voice_segment(buffer_copy)
                    )
                    process_thread.daemon = True
                    process_thread.start()
            
            except Exception as e:
                self.update_status(f"Audio callback error: {str(e)}")
                
        return (in_data, pyaudio.paContinue)
    
    def process_voice_segment(self, audio_buffer):
        """Process a segment of voice audio after detection"""
        try:
            # Temporarily stop listening while processing
            self.is_listening = False
            self.update_status("Processing speech...")
            
            # Combine audio chunks
            audio_data = b''.join(audio_buffer)
            
            # Save as temporary WAV file
            temp_wav = io.BytesIO()
            with wave.open(temp_wav, 'wb') as wf:
                wf.setnchannels(CHANNELS)
                wf.setsampwidth(2)  # 16-bit audio
                wf.setframerate(RATE)
                wf.writeframes(audio_data)
            
            temp_wav.seek(0)
            
            # Add to transcription queue
            self.audio_queue.put(temp_wav)
            
        except Exception as e:
            self.update_status(f"Voice processing error: {str(e)}")
        finally:
            # Resume listening
            self.is_listening = True
    
    def process_transcriptions(self):
        """Process audio files in the queue and get transcriptions"""
        while self.running:
            try:
                # Get audio file from queue (if any)
                try:
                    audio_file = self.audio_queue.get(timeout=1)
                except queue.Empty:
                    continue
                
                # Transcribe the audio
                transcript = self.transcribe_audio(audio_file)
                
                if transcript and transcript.strip():
                    # Add to transcription queue for AI processing
                    self.transcription_queue.put(transcript)
                    
                    # Process the transcription in another thread
                    process_thread = threading.Thread(
                        target=self.process_user_message
                    )
                    process_thread.daemon = True
                    process_thread.start()
                else:
                    # If no transcript, resume listening
                    self.update_status("Listening for speech...")
                
            except Exception as e:
                self.update_status(f"Transcription processing error: {str(e)}")
                traceback.print_exc()
                time.sleep(1)  # Avoid tight loops if there's an error
    
    def process_user_message(self):
        """Process user message and get AI response"""
        try:
            # Get transcript from queue
            transcript = self.transcription_queue.get(block=False)
            
            # Show user message
            self.add_to_chat("You", transcript)
            
            # Add to conversation history
            self.messages.append({"role": "user", "content": transcript})
            
            # Stop listening while AI is responding
            self.is_speaking = True
            
            # Get streaming response from AI
            self.current_response = ""
            self.add_to_chat("AI", "")  # Create an empty response that will be updated
            self.get_streaming_response()
            
        except queue.Empty:
            pass
        except Exception as e:
            self.update_status(f"Message processing error: {str(e)}")
            traceback.print_exc()
            self.is_speaking = False  # Make sure to reset this flag
    
    def transcribe_audio(self, audio_file):
        """Transcribe audio using the OpenAI Whisper API."""
        try:
            # Make a request to the Whisper API
            endpoint = "https://api.openai.com/v1/audio/transcriptions"
            
            # Reset file position
            audio_file.seek(0)
            
            # Use requests to make the API call
            response = requests.post(
                endpoint,
                headers={"Authorization": f"Bearer {OPENAI_API_KEY}"},
                files={"file": ("audio.wav", audio_file, "audio/wav")},
                data={"model": "whisper-1"}
            )
            
            if response.status_code == 200:
                return response.json().get("text", "")
            else:
                self.update_status(f"Transcription error: {response.text}")
                return None
        except Exception as e:
            self.update_status(f"Transcription error: {str(e)}")
            return None
    
    def get_streaming_response(self):
        """Get a streaming response from the AI using the OpenAI API."""
        try:
            model = self.model_var.get()
            
            # Make a request to the Chat Completions API with streaming enabled
            endpoint = "https://api.openai.com/v1/chat/completions"
            
            payload = {
                "model": model,
                "messages": self.messages,
                "stream": True,
                "max_tokens": 150
            }
            
            headers = {
                "Authorization": f"Bearer {OPENAI_API_KEY}",
                "Content-Type": "application/json"
            }
            
            # Start speaking thread
            speak_thread = threading.Thread(target=self.stream_speak)
            speak_thread.daemon = True
            speak_thread.start()
            
            full_response = ""
            current_sentence = ""
            
            # Make the streaming API call
            with requests.post(endpoint, json=payload, headers=headers, stream=True) as response:
                if response.status_code != 200:
                    self.update_status(f"Streaming error: {response.text}")
                    self.is_speaking = False
                    return
                
                # Process each chunk as it arrives
                for line in response.iter_lines():
                    if not self.running:
                        break
                        
                    if line:
                        line = line.decode('utf-8')
                        if line.startswith('data: ') and line != 'data: [DONE]':
                            json_str = line[6:]  # Remove 'data: ' prefix
                            try:
                                chunk = json.loads(json_str)
                                content = chunk.get('choices', [{}])[0].get('delta', {}).get('content', '')
                                if content:
                                    full_response += content
                                    current_sentence += content
                                    
                                    # Check if we have a sentence ending
                                    if any(current_sentence.rstrip().endswith(end) for end in ['.', '!', '?', ':', ';']):
                                        # Add complete sentence to TTS queue
                                        self.tts_engine.say(current_sentence)
                                        self.tts_engine.runAndWait()
                                        current_sentence = ""
                                    
                                    # Update the chat display with the current response
                                    self.update_response(full_response)
                            except json.JSONDecodeError:
                                pass  # Skip invalid JSON
            
            # Speak any remaining text
            if current_sentence.strip():
                self.tts_engine.say(current_sentence)
                self.tts_engine.runAndWait()
            
            # Complete the response
            self.messages.append({"role": "assistant", "content": full_response})
            self.is_speaking = False
            self.update_status("Listening for speech...")
            
        except Exception as e:
            self.update_status(f"Streaming error: {str(e)}")
            self.is_speaking = False
            traceback.print_exc()
    
    def stream_speak(self):
        """Monitor current response and speak it in chunks as it's generated."""
        while self.is_speaking and self.running:
            # The speaking is now handled in get_streaming_response
            # This thread just keeps running while speech is happening
            time.sleep(0.2)
    
    def update_response(self, text):
        """Update the AI response in the chat area in real-time."""
        self.root.after(0, lambda: self._update_ai_response(text))
    
    def _update_ai_response(self, text):
        """Internal method to update AI response."""
        # Find the last message from AI
        last_index = self.chat_area.search("AI:", "1.0", tk.END, backwards=True)
        if last_index:
            # Clear the current response
            line_start = last_index.split('.')[0]
            next_line = int(line_start) + 1
            self.chat_area.delete(f"{next_line}.0", tk.END)
            
            # Insert the updated response
            self.chat_area.insert(f"{next_line}.0", f" {text}\n")
            self.chat_area.see(tk.END)
    
    def add_to_chat(self, speaker, message):
        """Add a message to the chat display."""
        self.root.after(0, lambda: self._update_chat(speaker, message))
    
    def _update_chat(self, speaker, message):
        """Internal method to update chat display."""
        self.chat_area.insert(tk.END, f"\n{speaker}:")
        if message:
            self.chat_area.insert(tk.END, f" {message}\n")
        self.chat_area.see(tk.END)  # Auto-scroll to the bottom
    
    def update_status(self, message):
        """Update the status label with thread safety."""
        self.root.after(0, lambda: self.status_label.config(text=message))

if __name__ == "__main__":
    try:
        # Start the application
        root = tk.Tk()
        app = VoiceChatApp(root)
        root.mainloop()
    except Exception as e:
        print(f"Application error: {e}")
        traceback.print_exc() 