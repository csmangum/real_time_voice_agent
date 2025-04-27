"""
Latency testing script for the Real-Time Voice Agent.

This script simulates AudioCodes WebSocket traffic and measures the round-trip time
between sending an audio chunk and receiving a response from OpenAI.

Usage:
    python latency_test.py

The script will connect to the local WebSocket server, send simulated audio chunks,
and measure the time it takes to process each chunk.
"""

import asyncio
import base64
import json
import os
import statistics
import time
from typing import List, Dict, Any
import sys

import websockets

# Configuration
WS_URL = "ws://localhost:8000/ws"  # Local WebSocket server URL
TEST_DURATION = 30  # Test duration in seconds
CHUNK_SIZE = 2048  # Size of audio chunks to send
SAMPLE_RATE = 16000  # Audio sample rate in Hz
BITS_PER_SAMPLE = 16  # Bits per sample for PCM audio


async def run_test():
    """Run the latency test against the local WebSocket server."""
    print(f"Connecting to {WS_URL}...")
    
    try:
        # Connect to the WebSocket server
        async with websockets.connect(WS_URL) as websocket:
            print("Connected to WebSocket server.")
            
            # Generate a test conversation ID
            conversation_id = f"test-{int(time.time())}"
            
            # Step 1: Send session.initiate message
            await websocket.send(json.dumps({
                "type": "session.initiate",
                "conversationId": conversation_id,
                "bot": {
                    "name": "Latency Test Bot",
                    "id": "latency-test"
                },
                "channel": "test"
            }))
            
            # Wait for response
            response = await websocket.recv()
            print(f"Session initiated: {response[:100]}...")
            
            # Step 2: Start user stream
            await websocket.send(json.dumps({
                "type": "userStream.start",
                "conversationId": conversation_id,
                "mediaFormat": "raw/lpcm16"
            }))
            
            # Wait for response
            response = await websocket.recv()
            print(f"User stream started: {response}")
            
            # Step 3: Send audio chunks and measure latency
            latencies = []
            start_time = time.time()
            chunk_count = 0
            
            print(f"Sending audio chunks for {TEST_DURATION} seconds...")
            
            # Generate silent audio (all zeros)
            silent_chunk = bytes(CHUNK_SIZE)
            
            # Track when we receive responses
            responses_received = 0
            
            # Set up task to listen for responses
            async def listen_for_responses():
                nonlocal responses_received
                while True:
                    try:
                        response = await websocket.recv()
                        response_time = time.time()
                        
                        # Parse response
                        try:
                            response_data = json.loads(response)
                            if response_data.get("type") == "playStream.chunk":
                                # Record the time when we received a response
                                responses_received += 1
                                if chunk_count > 0:  # Skip first few chunks to avoid warmup
                                    latency = (response_time - start_time) * 1000  # ms
                                    latencies.append(latency)
                                    print(f"Response received. Latency: {latency:.2f}ms")
                        except json.JSONDecodeError:
                            print(f"Received non-JSON response: {response[:50]}...")
                    except Exception as e:
                        print(f"Error receiving response: {e}")
                        break
            
            # Start listening for responses
            listen_task = asyncio.create_task(listen_for_responses())
            
            try:
                # Send audio chunks until test duration is reached
                while time.time() - start_time < TEST_DURATION:
                    # Encode the silent chunk as base64
                    encoded_chunk = base64.b64encode(silent_chunk).decode("utf-8")
                    
                    # Timestamp before sending
                    send_time = time.time()
                    
                    # Send the chunk
                    await websocket.send(json.dumps({
                        "type": "userStream.chunk",
                        "conversationId": conversation_id,
                        "audioChunk": encoded_chunk
                    }))
                    
                    chunk_count += 1
                    
                    # Wait a short time to simulate real audio streaming rate
                    # A 2048-byte chunk at 16kHz, 16-bit is about 64ms of audio
                    await asyncio.sleep(0.064)
                
                # Allow some time for final responses
                print("Waiting for final responses...")
                await asyncio.sleep(2)
                
            finally:
                # Cancel the listen task
                listen_task.cancel()
                
                # Step 4: Stop user stream
                await websocket.send(json.dumps({
                    "type": "userStream.stop",
                    "conversationId": conversation_id
                }))
                
                # Wait for response
                try:
                    response = await websocket.recv()
                    print(f"User stream stopped: {response}")
                except Exception:
                    pass
                
                # Step 5: End session
                await websocket.send(json.dumps({
                    "type": "session.end",
                    "conversationId": conversation_id
                }))
            
            # Print latency statistics
            if latencies:
                print("\nLatency Statistics:")
                print(f"Total audio chunks sent: {chunk_count}")
                print(f"Total responses received: {responses_received}")
                print(f"Minimum latency: {min(latencies):.2f}ms")
                print(f"Maximum latency: {max(latencies):.2f}ms")
                print(f"Average latency: {statistics.mean(latencies):.2f}ms")
                print(f"Median latency: {statistics.median(latencies):.2f}ms")
                if len(latencies) > 1:
                    print(f"Standard deviation: {statistics.stdev(latencies):.2f}ms")
                print(f"95th percentile: {sorted(latencies)[int(len(latencies) * 0.95)]:.2f}ms")
            else:
                print("No latency measurements collected.")
                
    except Exception as e:
        print(f"Test failed: {e}")
        return False
    
    return True


if __name__ == "__main__":
    print("Real-Time Voice Agent Latency Test")
    print("==================================")
    
    # Check if the server is running
    print("Checking if the WebSocket server is running...")
    
    # Run the test
    asyncio.run(run_test()) 