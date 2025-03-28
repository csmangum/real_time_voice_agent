import asyncio
import websockets
import json
import pyaudio
import base64
import os
import wave
import tkinter as tk
from tkinter import ttk, scrolledtext
from dotenv import load_dotenv
import threading
import time
import ssl
from queue import Queue
import traceback
import sys
import requests
import io

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

# Newer model version that should be available to most accounts
MODEL_NAME = "gpt-4o-mini"

class RealtimeIntentApp:
    def __init__(self, root):
        self.root = root
        self.root.title("OpenAI Realtime Intent Classification")
        self.root.geometry("800x600")
        
        # Text display for intent
        self.text_area = scrolledtext.ScrolledText(self.root, wrap=tk.WORD, height=20, width=80)
        self.text_area.pack(padx=10, pady=10, fill=tk.BOTH, expand=True)
        
        # Status label
        self.status_label = ttk.Label(self.root, text="Not connected")
        self.status_label.pack(pady=5)
        
        # User transcript label
        self.transcript_label = ttk.Label(self.root, text="Your speech: ")
        self.transcript_label.pack(pady=5)
        
        # Intent label
        self.intent_heading = ttk.Label(self.root, text="CURRENT INTENT:", font=("Arial", 12, "bold"))
        self.intent_heading.pack(pady=5)
        
        # Control buttons
        self.button_frame = ttk.Frame(self.root)
        self.button_frame.pack(pady=10)
        
        self.start_button = ttk.Button(self.button_frame, text="Start Listening", command=self.start_listening)
        self.start_button.pack(side=tk.LEFT, padx=5)
        
        self.stop_button = ttk.Button(self.button_frame, text="Stop Listening", command=self.stop_listening, state=tk.DISABLED)
        self.stop_button.pack(side=tk.LEFT, padx=5)
        
        # Model selection dropdown
        self.model_label = ttk.Label(self.root, text="Select Model:")
        self.model_label.pack(pady=5)
        
        self.model_var = tk.StringVar(value=MODEL_NAME)
        self.model_dropdown = ttk.Combobox(self.root, textvariable=self.model_var)
        self.model_dropdown['values'] = ('gpt-4o-mini', 'gpt-4o', 'gpt-3.5-turbo')
        self.model_dropdown.pack(pady=5)
        
        # WebSocket connection
        self.websocket = None
        self.listening = False
        self.audio_thread = None
        self.current_intent = ""
        self.last_transcript = ""
        self.audio_queue = Queue()
        
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
        
    def start_listening(self):
        if not self.listening:
            self.listening = True
            self.start_button.config(state=tk.DISABLED)
            self.stop_button.config(state=tk.NORMAL)
            self.status_label.config(text="Connecting...")
            self.text_area.delete('1.0', tk.END)
            
            # Start WebSocket connection in a separate thread
            self.ws_thread = threading.Thread(target=self.run_websocket)
            self.ws_thread.daemon = True
            self.ws_thread.start()
    
    def stop_listening(self):
        if self.listening:
            self.listening = False
            self.start_button.config(state=tk.NORMAL)
            self.stop_button.config(state=tk.DISABLED)
            self.status_label.config(text="Stopped")
    
    def run_websocket(self):
        try:
            asyncio.run(self.connect_and_stream())
        except Exception as e:
            self.update_status(f"Websocket error: {str(e)}")
            traceback.print_exc()
    
    async def connect_and_stream(self):
        try:
            # Get the selected model
            model = self.model_var.get()
            
            # Use regular completions API instead of realtime since it's not widely available yet
            url = f"wss://api.openai.com/v1/chat/completions"
            
            # Headers for the connection
            headers = {
                "Authorization": f"Bearer {OPENAI_API_KEY}",
                "Content-Type": "application/json"
            }
            
            self.update_status(f"Using standard OpenAI API with {model}...")
            
            # Start recording audio in a separate thread
            self.audio_thread = threading.Thread(target=self.record_audio)
            self.audio_thread.daemon = True
            self.audio_thread.start()
            
            # Process audio and send requests
            await self.process_recording()
            
        except Exception as e:
            self.update_status(f"Connection error: {str(e)}")
            self.listening = False
            self.root.after(0, lambda: self.start_button.config(state=tk.NORMAL))
            self.root.after(0, lambda: self.stop_button.config(state=tk.DISABLED))
    
    async def process_recording(self):
        """Process recorded audio and analyze intent with the OpenAI API."""
        try:
            # Create task for recording audio
            self.update_status("Listening for speech...")
            
            # Process in a loop until stopped
            while self.listening:
                # Wait for audio to accumulate
                await asyncio.sleep(2)
                
                # If we have audio data, process it
                if not self.audio_queue.empty():
                    self.update_status("Processing speech...")
                    
                    # Get the latest audio buffer chunks (up to 5 seconds worth)
                    audio_chunks = []
                    chunk_count = 0
                    max_chunks = RATE * 5 // CHUNK  # About 5 seconds of audio
                    
                    while not self.audio_queue.empty() and chunk_count < max_chunks:
                        audio_chunks.append(self.audio_queue.get()["audio_buffer"])
                        chunk_count += 1
                    
                    if audio_chunks:
                        # Convert base64 chunks back to binary
                        binary_chunks = [base64.b64decode(chunk) for chunk in audio_chunks]
                        
                        # Save as temporary WAV file
                        temp_wav = io.BytesIO()
                        with wave.open(temp_wav, 'wb') as wf:
                            wf.setnchannels(CHANNELS)
                            wf.setsampwidth(2)  # 16-bit audio
                            wf.setframerate(RATE)
                            wf.writeframes(b''.join(binary_chunks))
                        
                        temp_wav.seek(0)
                        
                        # First transcribe the audio using Whisper API
                        try:
                            transcript = await self.transcribe_audio(temp_wav)
                            if transcript:
                                self.update_transcript(f"You said: {transcript}")
                                
                                # Get intent from the transcript
                                intent = await self.analyze_intent(transcript)
                                if intent:
                                    self.current_intent = intent
                                    self.update_intent_display(intent)
                        except Exception as e:
                            self.update_status(f"Processing error: {str(e)}")
                
                # If no longer listening, break the loop
                if not self.listening:
                    break
                    
        except Exception as e:
            self.update_status(f"Processing error: {str(e)}")
            self.listening = False
    
    async def transcribe_audio(self, audio_file):
        """Transcribe audio using the OpenAI Whisper API."""
        try:
            # Make a request to the Whisper API
            endpoint = "https://api.openai.com/v1/audio/transcriptions"
            
            # Reset file position
            audio_file.seek(0)
            
            # Use requests to make the API call
            response = await asyncio.to_thread(
                requests.post,
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
    
    async def analyze_intent(self, text):
        """Analyze the intent of the text using the OpenAI API."""
        try:
            model = self.model_var.get()
            
            # Make a request to the Chat Completions API
            endpoint = "https://api.openai.com/v1/chat/completions"
            
            payload = {
                "model": model,
                "messages": [
                    {"role": "system", "content": "You are an intent classifier. Analyze the user's speech and identify their intent. Respond with only the intent, no explanations."},
                    {"role": "user", "content": text}
                ],
                "max_tokens": 50
            }
            
            # Use requests to make the API call
            response = await asyncio.to_thread(
                requests.post,
                endpoint,
                headers={
                    "Authorization": f"Bearer {OPENAI_API_KEY}",
                    "Content-Type": "application/json"
                },
                json=payload
            )
            
            if response.status_code == 200:
                result = response.json()
                return result.get("choices", [{}])[0].get("message", {}).get("content", "")
            else:
                self.update_status(f"Intent analysis error: {response.text}")
                return None
        except Exception as e:
            self.update_status(f"Intent analysis error: {str(e)}")
            return None
    
    def record_audio(self):
        """Record audio and add it to the queue for sending."""
        p = pyaudio.PyAudio()
        
        # Open the audio stream
        stream = p.open(format=FORMAT,
                      channels=CHANNELS,
                      rate=RATE,
                      input=True,
                      frames_per_buffer=CHUNK)
        
        self.update_status("Started recording...")
        
        try:
            while self.listening:
                # Read audio data
                data = stream.read(CHUNK, exception_on_overflow=False)
                
                # Encode audio data to base64
                audio_data_b64 = base64.b64encode(data).decode('utf-8')
                
                # Create message and add to queue
                message = {
                    "type": "input_audio_buffer.append",
                    "audio_buffer": audio_data_b64,
                    "sample_rate": RATE
                }
                
                # Add to queue for async sending
                self.audio_queue.put(message)
                
                # Add a small delay to avoid overflowing the queue
                time.sleep(0.01)
        
        except Exception as e:
            self.update_status(f"Audio recording error: {str(e)}")
        finally:
            # Close the audio stream
            stream.stop_stream()
            stream.close()
            p.terminate()
            self.update_status("Recording stopped")
    
    def update_status(self, message):
        """Update the status label with thread safety."""
        self.root.after(0, lambda: self.status_label.config(text=message))
    
    def update_transcript(self, text):
        """Update the transcript label with thread safety."""
        self.root.after(0, lambda: self.transcript_label.config(text=text))
    
    def update_intent_display(self, text):
        """Update the intent display with thread safety."""
        self.root.after(0, lambda: self._update_text(text))
    
    def _update_text(self, text):
        """Internal method to update text display."""
        self.text_area.delete('1.0', tk.END)
        self.text_area.insert(tk.END, text)
        self.text_area.see(tk.END)  # Auto-scroll to the bottom

if __name__ == "__main__":
    # Print websockets version
    print(f"Using websockets version: {websockets.__version__}")
    
    # Check Python version 
    print(f"Python version: {sys.version}")
    
    try:
        # Start the application
        root = tk.Tk()
        app = RealtimeIntentApp(root)
        root.mainloop()
    except Exception as e:
        print(f"Application error: {e}")
        traceback.print_exc()
