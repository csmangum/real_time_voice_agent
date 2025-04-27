# Latency Optimizations for Real-Time Voice Agent

This document outlines the optimizations made to minimize latency in the Real-Time Voice Agent system, ensuring smooth, real-time conversations between callers and the AI assistant.

## Overview

The Real-Time Voice Agent system bridges AudioCodes VoiceAI Connect with OpenAI's Realtime API for speech-to-speech conversation. For natural conversations, latency should be kept below 200-300ms. The following optimizations have been implemented to achieve this goal.

## WebSocket Configuration Optimizations

### FastAPI/Uvicorn Server Settings

The server has been configured with the following optimizations in `run.py` and `app/main.py`:

- **Smaller WebSocket Buffer Sizes**: Prevents audio chunks from being queued before sending
- **Frequent Ping Intervals (5s)**: Ensures connections remain healthy
- **HTTP/1.1 Protocol**: Lower overhead than HTTP/2 for WebSocket connections
- **Disabled Access Logging**: Reduces processing overhead
- **Larger Maximum Message Size**: Accommodates audio chunks without fragmentation

### TCP Socket Optimizations

In `app/websocket_manager.py`, we've added TCP-level socket optimizations:

- **Disabled Nagle's Algorithm**: Enables TCP_NODELAY to send packets immediately without buffering
- **Fast-Path for Audio Chunks**: Special handling for audio chunk messages to bypass validation overhead
- **Socket Optimization Function**: Added the `_optimize_socket` method to configure WebSocket connections

## OpenAI Client Optimizations

The `app/bot/realtime_api.py` file has been updated with:

- **Limited Queue Size**: Prevents buffering of audio chunks
- **Efficient WebSocket Configuration**: Optimized settings for low-latency real-time streaming
- **TCP Socket Optimization**: Disabled Nagle's algorithm on the OpenAI WebSocket connection
- **Fast Audio Reception**: Added `get_nowait()` to avoid blocking when processing audio chunks

## Protocol Conversion Optimization

The bridge between AudioCodes and OpenAI in `app/bot/audiocodes_realtime_bridge.py` has been optimized:

- **Minimized Conversion Steps**: Streamlined audio format conversion 
- **Pre-constructed Message Templates**: Reduced JSON construction overhead
- **Latency Measurement**: Added timing for each operation to identify bottlenecks
- **Parallel Response Processing**: Used tasks to handle responses efficiently
- **Connection Event Handlers**: Improved recovery from network disruptions

## Audio Stream Handling Improvements

In `app/handlers/stream_handlers.py`, we've made these improvements:

- **Smaller Chunk Size**: Reduced from 4000 to 2048 bytes for lower latency
- **Parallel Chunk Processing**: Used `asyncio.create_task()` and `gather()` for concurrent processing
- **Minimal Validation**: Fast-path for audio chunks skips unnecessary validation
- **Timestamp Tracking**: Measures processing time for each audio chunk

## Latency Monitoring

To help identify and address latency issues:

- **Health Endpoint**: Updated to report latency metrics (avg, min, max, median)
- **Latency Test Script**: Added `latency_test.py` to benchmark the system under load
- **Debug Logging**: Added conditional logging for operations that exceed time thresholds

## Using the Latency Test

The `latency_test.py` script can be used to measure end-to-end latency:

```powershell
# Start the server
python run.py

# In a different terminal, run the latency test
python latency_test.py
```

The test will simulate AudioCodes audio streaming and report statistics on round-trip latency.

## Recommendations for Deployment

For minimal latency in production:

1. **Network Proximity**: Deploy the server close to AudioCodes infrastructure
2. **Server Resources**: Ensure adequate CPU for real-time processing
3. **Dedicated Network**: Use network interfaces with low jitter and latency
4. **Monitoring**: Use the `/health` endpoint to track latency over time
5. **Chunk Size Adjustment**: Tune `DEFAULT_CHUNK_SIZE` (in `stream_handlers.py`) based on network conditions

## Further Optimization Opportunities

Potential areas for further latency reduction:

- **WebAssembly for Encoding/Decoding**: Faster base64 operations
- **Custom WebSocket Implementation**: Lower-level control than provided by libraries
- **Network QoS**: Prioritize WebSocket traffic on production infrastructure
- **Regional Deployment**: Place servers in regions closest to AudioCodes and OpenAI endpoints 