# Voice Agent Prototype: Implementation Plan

## Core Functionality

1. Direct voice input/output with state management
2. Tool invocation based on model responses
3. Stateful conversation tracking
4. Simple example scenario (banking card replacement)

## Phase 1: Setup and Core Architecture

1. **Environment Configuration**
   - Create project directory and environment
   - Set up configuration file for API keys
   - Install dependencies: `websockets`, `pyaudio`, `numpy`, etc.

2. **Agent State Structure**
   - Define JSON schema for agent state
   - Create state management utility functions
   - Implement state persistence mechanism

3. **Tools Framework**
   - Define tool interface and registry
   - Implement sample tools (identity verification, account lookup)
   - Create tool execution engine

## Phase 2: Audio Processing Pipeline

1. **Audio Recording**
   - Implement 24kHz, 16-bit PCM mono recording
   - Create audio chunking mechanism
   - Build base64 encoding utilities

2. **Audio Playback**
   - Implement streaming audio player
   - Create audio format conversion utilities
   - Build buffer management for smooth playback

3. **Audio Processing Utilities**
   - Implement silence detection
   - Create audio normalization functions
   - Build speech detection heuristics

## Phase 3: OpenAI Realtime API Integration

1. **WebSocket Client**
   - Implement connection handling
   - Create event processing pipeline
   - Build message formatting utilities

2. **API Events**
   - Implement handlers for all relevant server events
   - Create client event generators
   - Build session management logic

3. **System Prompt Design**
   - Create effective system prompt for voice agent
   - Define format for state management in responses
   - Structure tool invocation patterns

## Phase 4: Test Scenario Implementation

1. **Card Replacement Flow**
   - Define conversation stages
   - Implement state transitions
   - Create tool integration points

2. **Sample Interactions**
   - Create test cases for common paths
   - Implement edge case handling
   - Build recovery mechanisms

## Phase 5: Integration and Testing

1. **Main Application**
   - Implement main application loop
   - Create simple UI for testing/validation
   - Build logging and debugging tools

2. **Testing Framework**
   - Create automated test cases
   - Implement recording/playback for regression testing
   - Build validation mechanism for state transitions

## Implementation Details

### Agent State Schema
```json
{
  "session_id": "unique_id",
  "conversation": {
    "context": "card_replacement",
    "stage": "verification",
    "entities": {
      "card_type": "debit",
      "verification_status": "pending"
    }
  },
  "user": {
    "verified": false,
    "preferences": {}
  },
  "tools": {
    "available": ["verify_identity", "check_account", "order_card"],
    "last_called": null,
    "results": {}
  }
}
```

### Realtime API Event Flow
1. Connect to WebSocket
2. Initialize session
3. Send audio chunks + state
4. Process response:
   - Extract audio response
   - Extract state updates
   - Execute any tool calls
   - Update local state
5. Repeat from step 3

### Sample Code Structure
```
voice-agent/
├── config.py                # Configuration and settings
├── agent_state.py           # State management 
├── audio_utils.py           # Audio recording/playback
├── realtime_client.py       # OpenAI Realtime API client
├── tools/                   # Tool implementations
│   ├── __init__.py          
│   ├── identity.py          # Identity verification
│   ├── account.py           # Account management
│   └── cards.py             # Card operations
├── ui.py                    # Simple UI for testing
└── main.py                  # Main application logic
```

## 1. Core Architecture

### Agent State Management
```python
class AgentState:
    def __init__(self):
        self.session_id = f"session_{int(time.time())}"
        self.context = {
            "current_topic": "unknown",
            "current_step": "greeting",
            "previous_steps": [],
            "entities": {},
            "confirmation_needed": False,
            "confidence_level": "high"
        }
        self.user_profile = {
            "verified": False,
            "account_checked": False,
            "preferences": {}
        }
        self.tools = {
            "available": ["verify_identity", "check_account", "request_card"],
            "pending": [],
            "completed": [],
            "results": {}
        }
    
    def to_dict(self):
        return {
            "session_id": self.session_id,
            "context": self.context,
            "user_profile": self.user_profile,
            "tools": self.tools
        }
    
    def update_from_dict(self, state_update):
        """Apply partial updates to the state"""
        if "context" in state_update:
            self.context.update(state_update["context"])
        if "user_profile" in state_update:
            self.user_profile.update(state_update["user_profile"])
        if "tools" in state_update:
            # Handle special case for tools since we need to track history
            if "pending" in state_update["tools"]:
                self.tools["pending"] = state_update["tools"]["pending"]
            if "results" in state_update["tools"]:
                self.tools["results"].update(state_update["tools"]["results"])
```

### Tool Framework
```python
class ToolRegistry:
    def __init__(self):
        self.tools = {}
    
    def register(self, name, tool_function):
        self.tools[name] = tool_function
    
    async def execute(self, tool_name, arguments):
        if tool_name not in self.tools:
            return {"error": f"Tool {tool_name} not found"}
        
        try:
            result = await self.tools[tool_name](**arguments)
            return result
        except Exception as e:
            return {"error": str(e)}

# Sample tool implementations
async def verify_identity(user_id, verification_info=None):
    # Simulate identity verification
    await asyncio.sleep(0.5)  # Simulate API call
    return {
        "verified": True,
        "verification_level": "high",
        "timestamp": time.time()
    }

async def check_account(account_id=None):
    # Simulate account check
    await asyncio.sleep(0.5)  # Simulate API call
    return {
        "account_exists": True,
        "account_status": "active",
        "card_eligible": True,
        "current_cards": ["debit_card_ending_1234"]
    }

async def request_card(card_type="debit", shipping_address=None):
    # Simulate card request
    await asyncio.sleep(1.0)  # Simulate API call
    return {
        "request_id": f"req_{int(time.time())}",
        "card_type": card_type,
        "estimated_delivery": "3-5 business days",
        "status": "processing"
    }
```

## 2. OpenAI Realtime API Client

```python
class RealtimeAPIClient:
    def __init__(self, api_key, model="gpt-4o-realtime-preview-2024-10-01"):
        self.api_key = api_key
        self.model = model
        self.websocket = None
        self.response_audio_chunks = []
        self.response_text = ""
        self.state_updates = {}
        self.tool_calls = []
        
    async def connect(self):
        """Connect to the OpenAI Realtime API"""
        url = f"wss://api.openai.com/v1/realtime?model={self.model}"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "OpenAI-Beta": "realtime=v1"
        }
        
        self.websocket = await websockets.connect(url, extra_headers=headers)
        
        # Initialize session with system instructions
        await self.send_message({
            "type": "session.update",
            "session": {
                "instructions": """
                You are a voice banking assistant helping customers with card replacements and account services. 
                
                Respond in two parts:
                1. Communicate naturally with the customer via speech
                2. Maintain agent state through JSON updates
                
                Always listen carefully to users, ask for clarification when needed, and use appropriate tools.
                
                For state management, include in your responses:
                - Updated context information
                - Tool calls when appropriate
                - Any entity information extracted
                
                Available tools:
                - verify_identity: Check user identity
                - check_account: Retrieve account details
                - request_card: Place an order for a new card
                """
            }
        })
        
        # Create initial conversation
        await self.send_message({
            "type": "response.create",
            "response": {
                "modalities": ["text", "audio"]
            }
        })
        
        return self.websocket
    
    async def send_audio(self, audio_data_base64):
        """Send audio data to the API"""
        await self.send_message({
            "type": "input_audio_buffer.append",
            "audio": audio_data_base64,
            "format": {
                "type": "pcm16",
                "sample_rate": 24000
            }
        })
    
    async def send_agent_state(self, agent_state):
        """Send agent state to the API via a special message"""
        state_json = json.dumps(agent_state.to_dict())
        
        await self.send_message({
            "type": "conversation.item.create",
            "item": {
                "type": "message",
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": f"AGENT_STATE: {state_json}"
                    }
                ]
            }
        })
    
    async def commit_audio_and_get_response(self):
        """Commit the audio buffer and get a response"""
        # Clear previous response data
        self.response_audio_chunks = []
        self.response_text = ""
        self.state_updates = {}
        self.tool_calls = []
        
        # Commit the audio buffer
        await self.send_message({
            "type": "input_audio_buffer.commit"
        })
        
        # Create a response
        await self.send_message({
            "type": "response.create",
            "response": {
                "modalities": ["text", "audio"]
            }
        })
        
        # Process response events
        async for message in self.receive_messages():
            event_type = message.get("type", "")
            
            # Handle different event types
            if event_type == "response.audio.delta":
                self.response_audio_chunks.append(message.get("audio", ""))
            
            elif event_type == "response.text.delta":
                self.response_text += message.get("text", "")
                
                # Try to extract state updates and tool calls
                self._extract_state_and_tools()
            
            elif event_type == "response.done":
                break
        
        return {
            "audio": self.response_audio_chunks,
            "text": self.response_text,
            "state_updates": self.state_updates,
            "tool_calls": self.tool_calls
        }
    
    def _extract_state_and_tools(self):
        """Extract state updates and tool calls from response text"""
        try:
            # Look for JSON-formatted state updates
            state_pattern = r'AGENT_STATE_UPDATE:\s*(\{.*?\})'
            state_matches = re.findall(state_pattern, self.response_text, re.DOTALL)
            
            if state_matches:
                self.state_updates = json.loads(state_matches[-1])  # Use the last one
            
            # Look for tool calls
            tool_pattern = r'TOOL_CALL:\s*(\{.*?\})'
            tool_matches = re.findall(tool_pattern, self.response_text, re.DOTALL)
            
            self.tool_calls = [json.loads(tc) for tc in tool_matches]
                
        except json.JSONDecodeError:
            # If we can't parse the JSON yet, wait for more text
            pass
    
    async def send_message(self, message):
        """Send a message to the API"""
        if not self.websocket:
            raise Exception("Not connected to API")
        
        await self.websocket.send(json.dumps(message))
    
    async def receive_messages(self):
        """Receive and yield messages from the API"""
        if not self.websocket:
            raise Exception("Not connected to API")
        
        while True:
            try:
                message = await self.websocket.recv()
                yield json.loads(message)
            except websockets.exceptions.ConnectionClosed:
                break
    
    async def close(self):
        """Close the connection"""
        if self.websocket:
            await self.websocket.close()
            self.websocket = None
```

## 3. Audio Utilities

```python
class AudioManager:
    def __init__(self, sample_rate=24000, chunk_size=1024):
        self.sample_rate = sample_rate
        self.chunk_size = chunk_size
        self.py_audio = pyaudio.PyAudio()
        self.stream = None
        self.recording = False
        
    def start_recording(self):
        """Start recording audio"""
        self.recording = True
        self.stream = self.py_audio.open(
            format=pyaudio.paInt16,
            channels=1,
            rate=self.sample_rate,
            input=True,
            frames_per_buffer=self.chunk_size
        )
        
    def stop_recording(self):
        """Stop recording audio"""
        self.recording = False
        if self.stream:
            self.stream.stop_stream()
            self.stream.close()
            self.stream = None
            
    def read_chunk(self):
        """Read and encode a chunk of audio data"""
        if not self.stream or not self.recording:
            return None
            
        try:
            data = self.stream.read(self.chunk_size, exception_on_overflow=False)
            # Encode as base64
            return base64.b64encode(data).decode('utf-8')
        except Exception as e:
            print(f"Error reading audio: {e}")
            return None
            
    def play_audio(self, audio_chunks):
        """Play audio from base64-encoded chunks"""
        # Decode base64 chunks
        binary_chunks = [base64.b64decode(chunk) for chunk in audio_chunks]
        
        # Save as temporary WAV file
        temp_file = "temp_response.wav"
        with wave.open(temp_file, 'wb') as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(self.sample_rate)
            wf.writeframes(b''.join(binary_chunks))
        
        # Play using system's default player
        if sys.platform == "win32":
            os.startfile(temp_file)
        else:
            import subprocess
            opener = "open" if sys.platform == "darwin" else "xdg-open"
            subprocess.call([opener, temp_file])
```

## 4. Main Application Logic

```python
class VoiceAgentApp:
    def __init__(self):
        self.api_client = RealtimeAPIClient(OPENAI_API_KEY)
        self.audio_manager = AudioManager()
        self.agent_state = AgentState()
        self.tool_registry = ToolRegistry()
        self.setup_tools()
        
    def setup_tools(self):
        """Register available tools"""
        self.tool_registry.register("verify_identity", verify_identity)
        self.tool_registry.register("check_account", check_account)
        self.tool_registry.register("request_card", request_card)
        
    async def run(self):
        """Main application loop"""
        try:
            # Connect to the API
            await self.api_client.connect()
            print("Connected to OpenAI Realtime API")
            
            # Start recording audio
            self.audio_manager.start_recording()
            print("Started recording")
            
            # Main interaction loop
            while True:
                # Collect audio for 3 seconds
                audio_chunks = []
                start_time = time.time()
                while time.time() - start_time < 3:
                    chunk = self.audio_manager.read_chunk()
                    if chunk:
                        audio_chunks.append(chunk)
                        # Send each chunk to the API
                        await self.api_client.send_audio(chunk)
                    await asyncio.sleep(0.01)
                
                # Send agent state
                await self.api_client.send_agent_state(self.agent_state)
                
                # Get response
                response = await self.api_client.commit_audio_and_get_response()
                
                # Update agent state
                if response["state_updates"]:
                    self.agent_state.update_from_dict(response["state_updates"])
                
                # Execute tool calls
                for tool_call in response["tool_calls"]:
                    tool_name = tool_call.get("name", "")
                    tool_args = tool_call.get("arguments", {})
                    
                    if tool_name:
                        print(f"Executing tool: {tool_name}")
                        result = await self.tool_registry.execute(tool_name, tool_args)
                        
                        # Update agent state with tool results
                        self.agent_state.tools["pending"].remove(tool_name)
                        self.agent_state.tools["completed"].append(tool_name)
                        self.agent_state.tools["results"][tool_name] = result
                
                # Play response audio
                if response["audio"]:
                    self.audio_manager.play_audio(response["audio"])
                
                # Print response text and state
                print(f"Response: {response['text']}")
                print(f"Current State: {json.dumps(self.agent_state.to_dict(), indent=2)}")
                
        except KeyboardInterrupt:
            print("Stopping...")
        finally:
            # Clean up
            self.audio_manager.stop_recording()
            await self.api_client.close()
            print("Session ended")

# Run the application
if __name__ == "__main__":
    app = VoiceAgentApp()
    asyncio.run(app.run())
```

## 5. System Prompt Design

The system prompt is crucial for instructing the model on how to format responses. Here's a detailed version:

```
You are a voice banking assistant helping customers with card replacements and account services.

RESPONSE FORMAT:
Your responses must include two clear sections:

1. SPEECH: This is what you'll say to the customer. Be conversational and helpful.

2. AGENT_STATE_UPDATE: JSON object with updated state information, like:
{
  "context": {
    "current_topic": "card_replacement",
    "current_step": "verification",
    "entities": {
      "card_type": "debit"
    }
  },
  "user_profile": {
    "verified": false
  },
  "tools": {
    "pending": ["verify_identity"]
  }
}

3. TOOL_CALL: When appropriate, include tool calls in this format:
{
  "name": "verify_identity",
  "arguments": {
    "user_id": "detected_from_conversation"
  }
}

GUIDELINES:
- Always keep track of the conversation state
- Use tools when appropriate (verify_identity, check_account, request_card)
- Don't mention the formatting or state updates to the customer
- If the customer is asking about replacing a card, follow these steps:
  1. Verify their identity
  2. Check account eligibility
  3. Confirm card replacement details
  4. Submit the request
```

## 6. Sample Conversation Flow for Card Replacement

1. **Greeting & Intent Recognition**
   - **User**: "Hi, I need to replace my debit card."
   - **Agent State**: Sets current_topic to "card_replacement", current_step to "greeting"
   - **Agent Response**: Acknowledges request, explains verification process

2. **Identity Verification**
   - **Agent State**: Updates current_step to "verification", adds verify_identity to tools.pending
   - **Tool Call**: verify_identity with available user info
   - **User**: Provides verification info
   - **Agent State**: Updates user_profile.verified based on tool results

3. **Account Eligibility**
   - **Agent State**: Updates current_step to "account_check", adds check_account to tools.pending
   - **Tool Call**: check_account with account info
   - **Agent State**: Records eligibility in state

4. **Confirmation & Details**
   - **Agent State**: Updates current_step to "confirmation"
   - **Agent Response**: Confirms details and asks for shipping preferences
   - **User**: Provides or confirms shipping address

5. **Request Submission**
   - **Agent State**: Updates current_step to "submission", adds request_card to tools.pending
   - **Tool Call**: request_card with details
   - **Agent State**: Records request_id from tool response
   - **Agent Response**: Confirms submission, provides tracking info

## 8. Testing Strategy

1. **Unit Tests**
   - Test each component in isolation
   - Mock WebSocket connections for API testing
   - Verify state transitions and tool execution

2. **Integration Tests**
   - Test complete conversation flows
   - Use recorded audio samples for consistency
   - Validate state management across multiple turns

3. **Error Recovery Tests**
   - Test behavior with interrupted audio
   - Test recovery from connection failures
   - Test handling of unclear user requests

## 9. Metrics for Success

1. **Functional Metrics**
   - Successful completion of end-to-end flows
   - Correct tool execution at appropriate moments
   - Proper state tracking through conversation

2. **Performance Metrics**
   - Audio latency < 500ms
   - State processing time < 100ms
   - Tool execution time < 1s

3. **Quality Metrics**
   - Speech recognition accuracy > 95%
   - Appropriate contextual responses > 90%
   - Conversation completion rate > 85%
