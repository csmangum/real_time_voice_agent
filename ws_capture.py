"""
WebSocket Traffic Capture Script

This script creates a WebSocket server that acts as a proxy between your client and the OpenAI Realtime API.
It logs all traffic in both directions to help debug connection issues.

Usage:
    python ws_capture.py

After starting this script, modify your application to connect to:
    ws://localhost:8765 instead of wss://api.openai.com/v1/realtime

All traffic, headers and messages will be logged to console and to a capture log file.
"""

import asyncio
import websockets
import logging
import json
import ssl
import time
import os
import argparse
from datetime import datetime
from pathlib import Path

# Configure command line arguments
parser = argparse.ArgumentParser(description="WebSocket proxy for debugging OpenAI Realtime API")
parser.add_argument("--port", type=int, default=8765, help="Port to run the proxy server on")
parser.add_argument("--host", type=str, default="localhost", help="Host to bind the proxy server to")
parser.add_argument("--target", type=str, default="wss://api.openai.com/v1/realtime", 
                    help="Target WebSocket server URL")
args = parser.parse_args()

# Configure logging
log_dir = Path("ws_logs")
log_dir.mkdir(exist_ok=True)
log_file = log_dir / f"ws_capture_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

# Set up file handler
file_handler = logging.FileHandler(log_file)
file_handler.setLevel(logging.DEBUG)
file_formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
file_handler.setFormatter(file_formatter)

# Set up console handler
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
console_formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
console_handler.setFormatter(console_formatter)

# Configure logger
logger = logging.getLogger("ws_proxy")
logger.setLevel(logging.DEBUG)
logger.addHandler(file_handler)
logger.addHandler(console_handler)

# Global connection counter
connection_count = 0

async def forward_messages(source, destination, direction, conn_id):
    """Forward messages from source to destination WebSocket and log them."""
    try:
        async for message in source:
            # Log the message
            if isinstance(message, bytes):
                logger.debug(f"[{conn_id}] {direction} BINARY: {len(message)} bytes")
                # Try to parse as JSON if it looks like a text message
                try:
                    if message.startswith(b'{') and message.endswith(b'}'):
                        text = message.decode('utf-8')
                        data = json.loads(text)
                        logger.debug(f"[{conn_id}] {direction} JSON: {text}")
                except Exception:
                    # Just log the first few bytes as hex
                    preview = ' '.join(f'{b:02x}' for b in message[:20])
                    logger.debug(f"[{conn_id}] {direction} BINARY PREVIEW: {preview}...")
            else:
                logger.debug(f"[{conn_id}] {direction} TEXT: {message}")
                # Try to pretty-print if it's JSON
                try:
                    data = json.loads(message)
                    logger.debug(f"[{conn_id}] {direction} JSON: {json.dumps(data, indent=2)}")
                except Exception:
                    pass
            
            # Forward the message
            try:
                await destination.send(message)
                logger.debug(f"[{conn_id}] {direction} message forwarded successfully")
            except Exception as e:
                logger.error(f"[{conn_id}] Error forwarding {direction} message: {e}")
                break
                
    except websockets.exceptions.ConnectionClosed as e:
        logger.info(f"[{conn_id}] {direction} connection closed: code={e.code}, reason={e.reason}")
    except Exception as e:
        logger.error(f"[{conn_id}] Error in {direction} forwarding: {e}")


async def proxy_handler(websocket, path):
    """Handle a WebSocket connection by proxying to the target server."""
    global connection_count
    connection_count += 1
    conn_id = f"CONN-{connection_count}"
    
    # Extract query parameters from path
    query = ""
    if '?' in path:
        query = path[path.index('?'):]
    
    target_url = f"{args.target}{query}"
    
    logger.info(f"[{conn_id}] New connection from client, forwarding to {target_url}")
    
    # Get headers to forward
    headers = {}
    for key, value in websocket.request_headers.items():
        if key.lower() in ('authorization', 'openai-beta', 'user-agent'):
            headers[key] = value
            # Mask API key for security in logs
            if key.lower() == 'authorization':
                masked_value = value[:15] + '...' + value[-5:] if len(value) > 25 else value
                logger.info(f"[{conn_id}] Header: {key}: {masked_value}")
            else:
                logger.info(f"[{conn_id}] Header: {key}: {value}")
    
    try:
        # Connect to target WebSocket server
        connection_start = time.time()
        logger.info(f"[{conn_id}] Connecting to target server...")
        
        # Create an SSL context that doesn't verify certificates for testing
        ssl_context = ssl.create_default_context()
        
        target_ws = await websockets.connect(
            target_url, 
            ssl=ssl_context, 
            extra_headers=headers,
            ping_interval=5,
            ping_timeout=20,
            max_size=16 * 1024 * 1024,  # 16MB to handle large messages
            close_timeout=5
        )
        
        connection_time = time.time() - connection_start
        logger.info(f"[{conn_id}] Connected to target in {connection_time:.2f}s")
        
        # Create tasks for bidirectional forwarding
        client_to_target = asyncio.create_task(
            forward_messages(websocket, target_ws, "CLIENT -> TARGET", conn_id)
        )
        target_to_client = asyncio.create_task(
            forward_messages(target_ws, websocket, "TARGET -> CLIENT", conn_id)
        )
        
        # Wait for either forwarding direction to complete
        done, pending = await asyncio.wait(
            [client_to_target, target_to_client],
            return_when=asyncio.FIRST_COMPLETED
        )
        
        # Cancel the pending task
        for task in pending:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        
        logger.info(f"[{conn_id}] Proxy session ended")
    
    except Exception as e:
        logger.error(f"[{conn_id}] Error setting up proxy: {e}")
    
    finally:
        logger.info(f"[{conn_id}] Connection closed")


async def start_server():
    """Start the WebSocket proxy server."""
    server = await websockets.serve(
        proxy_handler, 
        args.host, 
        args.port,
        ping_interval=None,  # Let the client handle pings
        max_size=16 * 1024 * 1024  # 16MB to handle large messages
    )
    
    logger.info(f"WebSocket proxy server started on ws://{args.host}:{args.port}")
    logger.info(f"Forwarding to {args.target}")
    logger.info(f"Logging to {log_file}")
    logger.info("Press Ctrl+C to stop the server")
    
    # Keep the server running
    await server.wait_closed()


if __name__ == "__main__":
    try:
        asyncio.run(start_server())
    except KeyboardInterrupt:
        print("\nServer stopped by user")
    except Exception as e:
        logger.error(f"Server error: {e}") 