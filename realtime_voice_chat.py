import asyncio
import base64
import json
import os
import sys
import threading
import time
import tkinter as tk
import traceback
import wave
import numpy as np
import pyaudio
import websockets
from queue import Queue
from tkinter import ttk, scrolledtext
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Setup OpenAI API Key
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
if not OPENAI_API_KEY:
    raise ValueError("No OpenAI API key found. Please set the OPENAI_API_KEY environment variable.")

# Audio config
CHUNK = 1024
FORMAT = pyaudio.paInt16
CHANNELS = 1
RATE = 24000  # OpenAI Realtime API prefers 24kHz sample rate

# Realtime API config
REALTIME_API_URL = "wss://api.openai.com/v1/realtime"
MODEL = "gpt-4o-realtime-preview"  # Realtime model name

class RealtimeVoiceChatApp:
    def __init__(self, root):
        self.root = root
        self.root.title("OpenAI Realtime Voice Chat")
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
        
        self.model_var = tk.StringVar(value=MODEL)
        self.model_dropdown = ttk.Combobox(self.root, textvariable=self.model_var)
        self.model_dropdown['values'] = ('gpt-4o-realtime-preview', 'gpt-4o-mini-realtime-preview')
        self.model_dropdown.pack(pady=5)
        
        # Voice selection dropdown
        self.voice_label = ttk.Label(self.root, text="Select Voice:")
        self.voice_label.pack(pady=5)
        
        self.voice_var = tk.StringVar(value="alloy")
        self.voice_dropdown = ttk.Combobox(self.root, textvariable=self.voice_var)
        self.voice_dropdown['values'] = ('alloy', 'echo', 'fable', 'onyx', 'nova', 'shimmer')
        self.voice_dropdown.pack(pady=5)
        
        # Audio interface
        self.p = pyaudio.PyAudio()
        self.input_stream = None
        self.output_stream = None
        
        # Connection
        self.websocket = None
        self.running = False
        self.audio_queue = Queue()
        self.output_audio_queue = Queue()
        
        # Audio playback thread
        self.playback_thread = None
        
    async def connect_to_realtime_api(self):
        """Connect to the OpenAI Realtime API"""
        try:
            model = self.model_var.get()
            url = f"{REALTIME_API_URL}?model={model}"
            
            headers = {
                "Authorization": f"Bearer {OPENAI_API_KEY}",
                "OpenAI-Beta": "realtime=v1"
            }
            
            self.update_status(f"Connecting to OpenAI Realtime API with {model}...")
            
            # Connect to the WebSocket with correct headers parameter
            extra_headers = [
                ("Authorization", f"Bearer {OPENAI_API_KEY}"),
                ("OpenAI-Beta", "realtime=v1")
            ]
            self.websocket = await websockets.connect(url, extra_headers=extra_headers)
            
            # Initialize the session with both text and audio modalities
            voice = self.voice_var.get()
            await self.websocket.send(json.dumps({
                "type": "session.update",
                "session": {
                    "modalities": ["text", "audio"],
                    "voice": voice
                }
            }))
            
            # Start a response to initialize the conversation
            await self.websocket.send(json.dumps({
                "type": "response.create",
                "response": {
                    "modalities": ["text", "audio"],
                    "instructions": "You are a helpful voice assistant. Introduce yourself briefly."
                }
            }))
            
            self.update_status("Connected to OpenAI Realtime API. Starting conversation...")
            self.add_to_chat("System", "Connection established. You can speak now...")
            
            return True
            
        except Exception as e:
            self.update_status(f"Connection error: {str(e)}")
            traceback.print_exc()
            return False
            
    def start_chat(self):
        """Start the voice chat session"""
        if not self.running:
            self.running = True
            self.start_button.config(state=tk.DISABLED)
            self.stop_button.config(state=tk.NORMAL)
            
            # Start WebSocket connection in a separate thread
            self.websocket_thread = threading.Thread(target=self.run_websocket)
            self.websocket_thread.daemon = True
            self.websocket_thread.start()
            
    def stop_chat(self):
        """Stop the voice chat session"""
        if self.running:
            self.running = False
            self.start_button.config(state=tk.NORMAL)
            self.stop_button.config(state=tk.DISABLED)
            self.status_label.config(text="Conversation ended")
            self.add_to_chat("System", "Conversation ended.")
            
            # Close streams
            if self.input_stream:
                self.input_stream.stop_stream()
                self.input_stream.close()
                self.input_stream = None
                
            if self.output_stream:
                self.output_stream.stop_stream()
                self.output_stream.close()
                self.output_stream = None
            
            # Close WebSocket connection
            if self.websocket:
                asyncio.run(self.websocket.close())
                self.websocket = None
    
    def run_websocket(self):
        """Run the WebSocket connection in an asyncio event loop"""
        try:
            asyncio.run(self.websocket_main())
        except Exception as e:
            self.update_status(f"WebSocket error: {str(e)}")
            traceback.print_exc()
            self.running = False
            self.root.after(0, lambda: self.start_button.config(state=tk.NORMAL))
            self.root.after(0, lambda: self.stop_button.config(state=tk.DISABLED))
    
    async def websocket_main(self):
        """Main WebSocket handler"""
        if await self.connect_to_realtime_api():
            # Start audio input and output
            self.start_audio_streams()
            
            # Start a thread to play received audio
            self.playback_thread = threading.Thread(target=self.play_audio)
            self.playback_thread.daemon = True
            self.playback_thread.start()
            
            # Process incoming messages and send audio concurrently
            audio_sender_task = asyncio.create_task(self.audio_sender_loop())
            message_processor_task = asyncio.create_task(self.message_processor_loop())
            
            # Wait for either task to complete (or be cancelled)
            done, pending = await asyncio.wait(
                [audio_sender_task, message_processor_task],
                return_when=asyncio.FIRST_COMPLETED
            )
            
            # Cancel the pending task
            for task in pending:
                task.cancel()
        
        # Clean up if we exit the loop
        self.stop_chat()
    
    async def audio_sender_loop(self):
        """Continuously send audio data to the WebSocket"""
        while self.running and self.websocket:
            try:
                # Process all available audio chunks
                audio_chunks = []
                while not self.audio_queue.empty():
                    # Get audio data from queue
                    audio_data = self.audio_queue.get()
                    audio_chunks.append(audio_data)
                    
                if audio_chunks:
                    # Process in batches to reduce websocket traffic
                    combined_data = b''.join(audio_chunks)
                    
                    # Convert to base64
                    audio_b64 = base64.b64encode(combined_data).decode('utf-8')
                    
                    # Send to WebSocket
                    message = {
                        "type": "input_audio_buffer.append",
                        "audio": audio_b64,
                        "sample_rate": RATE
                    }
                    
                    await self.websocket.send(json.dumps(message))
                
                # Small delay to avoid tight loop
                await asyncio.sleep(0.05)
                
            except Exception as e:
                self.update_status(f"Error sending audio: {str(e)}")
                traceback.print_exc()
                await asyncio.sleep(1)  # Longer delay if there's an error
    
    async def message_processor_loop(self):
        """Process incoming messages from the WebSocket"""
        while self.running and self.websocket:
            try:
                message = await self.websocket.recv()
                await self.process_message(message)
            except websockets.exceptions.ConnectionClosed:
                self.update_status("Connection closed by server")
                self.running = False
                break
            except Exception as e:
                self.update_status(f"Error processing message: {str(e)}")
                traceback.print_exc()
                await asyncio.sleep(1)
    
    async def process_message(self, message):
        """Process messages from the WebSocket"""
        try:
            msg = json.loads(message)
            msg_type = msg.get("type")
            
            # Handle different message types
            if msg_type == "session.created" or msg_type == "session.updated":
                self.update_status(f"Session {msg_type.split('.')[1]}")
                
            elif msg_type == "conversation.created":
                self.update_status("Conversation created")
                
            elif msg_type == "response.created":
                self.update_status("Response created")
                
            elif msg_type == "response.text.delta":
                # Display text as it's received
                text_delta = msg.get("delta", {}).get("text", "")
                if text_delta:
                    self.update_text_delta("AI", text_delta)
            
            elif msg_type == "response.audio.delta":
                # Queue audio data for playback
                audio_data = msg.get("delta", {}).get("audio", "")
                if audio_data:
                    # Decode base64 audio and add to the output queue
                    audio_bytes = base64.b64decode(audio_data)
                    self.output_audio_queue.put(audio_bytes)
            
            elif msg_type == "error":
                error_message = msg.get("message", "Unknown error")
                self.update_status(f"Error: {error_message}")
                self.add_to_chat("System", f"Error: {error_message}")
                
            elif msg_type == "input_audio_buffer.speech_started":
                self.update_status("Speech detected")
                
            elif msg_type == "input_audio_buffer.speech_stopped":
                self.update_status("Speech stopped")
                
                # Commit the audio buffer and request a response
                await self.websocket.send(json.dumps({
                    "type": "input_audio_buffer.commit"
                }))
                
                await self.websocket.send(json.dumps({
                    "type": "response.create",
                    "response": {
                        "modalities": ["text", "audio"]
                    }
                }))
            
            elif msg_type == "response.done":
                self.update_status("Response complete")
                
                # Add a newline to visually separate responses
                self.add_to_chat("", "")
                
        except json.JSONDecodeError:
            self.update_status("Error decoding message")
        except Exception as e:
            self.update_status(f"Error processing message: {str(e)}")
            traceback.print_exc()
    
    def start_audio_streams(self):
        """Start audio input and output streams"""
        try:
            # Input stream (microphone)
            self.input_stream = self.p.open(
                format=FORMAT,
                channels=CHANNELS,
                rate=RATE,
                input=True,
                frames_per_buffer=CHUNK,
                stream_callback=self.audio_input_callback
            )
            
            # Output stream (speakers)
            self.output_stream = self.p.open(
                format=FORMAT,
                channels=CHANNELS,
                rate=RATE,
                output=True,
                frames_per_buffer=CHUNK
            )
            
            self.input_stream.start_stream()
            self.update_status("Audio streams started")
            
        except Exception as e:
            self.update_status(f"Error starting audio streams: {str(e)}")
            traceback.print_exc()
    
    def audio_input_callback(self, in_data, frame_count, time_info, status):
        """Callback for audio input stream"""
        if self.running and self.websocket:
            # Add to queue for sending
            self.audio_queue.put(in_data)
        return (in_data, pyaudio.paContinue)
    
    def play_audio(self):
        """Play received audio data"""
        while self.running:
            try:
                if not self.output_audio_queue.empty() and self.output_stream:
                    # Get audio data from queue
                    audio_data = self.output_audio_queue.get()
                    
                    # Play through output stream
                    self.output_stream.write(audio_data)
                
                # Small delay to avoid tight loop
                time.sleep(0.01)
                
            except Exception as e:
                self.update_status(f"Error playing audio: {str(e)}")
                traceback.print_exc()
                time.sleep(1)  # Longer delay if there's an error
    
    def update_text_delta(self, speaker, text_delta):
        """Update the chat area with text deltas"""
        self.root.after(0, lambda: self._handle_text_delta(speaker, text_delta))
    
    def _handle_text_delta(self, speaker, text_delta):
        """Internal method to handle text deltas"""
        # Find if we already have a line for this speaker
        last_index = self.chat_area.search(f"{speaker}:", "1.0", tk.END, backwards=True)
        
        if last_index:
            # Add to existing line
            line_start = last_index.split('.')[0]
            text_start = f"{line_start}.{len(speaker) + 2}"  # +2 for ": "
            self.chat_area.insert(text_start, text_delta)
        else:
            # Create a new line
            self.add_to_chat(speaker, text_delta)
        
        self.chat_area.see(tk.END)
    
    def add_to_chat(self, speaker, message):
        """Add a message to the chat display"""
        self.root.after(0, lambda: self._update_chat(speaker, message))
    
    def _update_chat(self, speaker, message):
        """Internal method to update chat display"""
        if speaker:
            self.chat_area.insert(tk.END, f"\n{speaker}:")
            if message:
                self.chat_area.insert(tk.END, f" {message}")
        else:
            # Just insert a message without a speaker
            self.chat_area.insert(tk.END, f"\n{message}")
            
        self.chat_area.see(tk.END)  # Auto-scroll to the bottom
    
    def update_status(self, message):
        """Update the status label with thread safety"""
        self.root.after(0, lambda: self.status_label.config(text=message))

if __name__ == "__main__":
    try:
        # Start the application
        root = tk.Tk()
        app = RealtimeVoiceChatApp(root)
        root.mainloop()
    except Exception as e:
        print(f"Application error: {e}")
        traceback.print_exc() 