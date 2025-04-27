"""
Debug Utilities for WebSocket Analysis

This module provides helpers to analyze logs from the WebSocket proxy
and identify common issues with the OpenAI Realtime API connection.
"""

import re
import json
import argparse
from pathlib import Path
from datetime import datetime, timedelta

# Regular expressions for log parsing
LOG_LINE_PATTERN = re.compile(r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3}) - (\w+) - (.*)')
CONNECTION_ID_PATTERN = re.compile(r'\[CONN-(\d+)\]')
BINARY_SIZE_PATTERN = re.compile(r'BINARY: (\d+) bytes')
JSON_MESSAGE_PATTERN = re.compile(r'JSON: ({.*})')
CLOSE_CODE_PATTERN = re.compile(r'code=(\d+), reason=(.*)')
ERROR_PATTERN = re.compile(r'Error .* (.*)')


def parse_log_file(log_file):
    """Parse a WebSocket log file and extract event timeline."""
    events = []
    
    try:
        with open(log_file, 'r', encoding='utf-8') as f:
            for line in f:
                match = LOG_LINE_PATTERN.match(line.strip())
                if match:
                    timestamp_str, level, message = match.groups()
                    timestamp = datetime.strptime(timestamp_str, '%Y-%m-%d %H:%M:%S,%f')
                    
                    # Extract connection ID if present
                    conn_id_match = CONNECTION_ID_PATTERN.search(message)
                    conn_id = conn_id_match.group(1) if conn_id_match else None
                    
                    event = {
                        'timestamp': timestamp,
                        'level': level,
                        'message': message,
                        'conn_id': conn_id
                    }
                    
                    # Extract more info based on message type
                    if 'BINARY:' in message:
                        size_match = BINARY_SIZE_PATTERN.search(message)
                        if size_match:
                            event['binary_size'] = int(size_match.group(1))
                    
                    if 'JSON:' in message:
                        json_match = JSON_MESSAGE_PATTERN.search(message)
                        if json_match:
                            try:
                                event['json_data'] = json.loads(json_match.group(1))
                            except json.JSONDecodeError:
                                pass
                    
                    if 'connection closed' in message:
                        close_match = CLOSE_CODE_PATTERN.search(message)
                        if close_match:
                            event['close_code'] = int(close_match.group(1))
                            event['close_reason'] = close_match.group(2)
                    
                    if 'Error' in message:
                        error_match = ERROR_PATTERN.search(message)
                        if error_match:
                            event['error'] = error_match.group(1)
                    
                    events.append(event)
    except Exception as e:
        print(f"Error parsing log file: {e}")
    
    return events


def analyze_connection(events, conn_id=None):
    """Analyze a specific connection or all connections in the events."""
    if conn_id:
        conn_events = [e for e in events if e['conn_id'] == conn_id]
    else:
        # Find unique connection IDs
        conn_ids = set(e['conn_id'] for e in events if e['conn_id'])
        for cid in conn_ids:
            print(f"\nAnalyzing connection {cid}:")
            analyze_connection(events, cid)
        return
    
    if not conn_events:
        print(f"No events found for connection {conn_id}")
        return
    
    # Connection timeline
    start_time = min(e['timestamp'] for e in conn_events)
    end_time = max(e['timestamp'] for e in conn_events)
    duration = end_time - start_time
    
    print(f"Connection duration: {duration.total_seconds():.2f} seconds")
    
    # Look for client messages
    client_messages = [e for e in conn_events if 'CLIENT -> TARGET' in e['message']]
    print(f"Client sent {len(client_messages)} messages")
    
    # Look for server messages
    server_messages = [e for e in conn_events if 'TARGET -> CLIENT' in e['message']]
    print(f"Server sent {len(server_messages)} messages")
    
    # Look for binary audio data from server
    audio_chunks = [e for e in server_messages if 'BINARY:' in e['message']]
    if audio_chunks:
        total_audio_size = sum(e.get('binary_size', 0) for e in audio_chunks)
        print(f"Received {len(audio_chunks)} audio chunks, {total_audio_size} bytes total")
    else:
        print("No audio chunks received from server")
    
    # Check for errors
    error_events = [e for e in conn_events if 'level' in e and e['level'] == 'ERROR']
    if error_events:
        print(f"\nFound {len(error_events)} errors:")
        for e in error_events:
            print(f"  {e['timestamp']}: {e['message']}")
    
    # Check for close codes
    close_events = [e for e in conn_events if 'close_code' in e]
    if close_events:
        for e in close_events:
            print(f"\nConnection closed with code {e['close_code']}: {e['close_reason']}")
            print(f"  at {e['timestamp']} ({(e['timestamp'] - start_time).total_seconds():.2f}s into connection)")
    
    # Look for JSON messages with errors
    json_errors = [e for e in conn_events if 'json_data' in e and 
                  isinstance(e['json_data'], dict) and e['json_data'].get('type') == 'error']
    if json_errors:
        print("\nFound API errors in JSON responses:")
        for e in json_errors:
            print(f"  {e['timestamp']}: {e['json_data'].get('message', 'Unknown error')}")
    
    # Summarize activity timeline
    print("\nActivity timeline:")
    timeline = []
    
    # Connection establishment
    connect_event = next((e for e in conn_events if 'Connected to target' in e['message']), None)
    if connect_event:
        timeline.append((connect_event['timestamp'], "Connected to OpenAI server"))
    
    # First client message
    first_client_msg = next((e for e in client_messages), None)
    if first_client_msg:
        timeline.append((first_client_msg['timestamp'], "First client message sent"))
    
    # First server message
    first_server_msg = next((e for e in server_messages), None)
    if first_server_msg:
        timeline.append((first_server_msg['timestamp'], "First server message received"))
    
    # First audio chunk
    first_audio = next((e for e in audio_chunks), None)
    if first_audio:
        timeline.append((first_audio['timestamp'], f"First audio chunk received ({first_audio.get('binary_size', 0)} bytes)"))
    
    # Last audio chunk
    last_audio = audio_chunks[-1] if audio_chunks else None
    if last_audio and last_audio != first_audio:
        timeline.append((last_audio['timestamp'], f"Last audio chunk received ({last_audio.get('binary_size', 0)} bytes)"))
    
    # Connection close
    close_event = next((e for e in conn_events if 'connection closed' in e['message']), None)
    if close_event:
        timeline.append((close_event['timestamp'], f"Connection closed"))
    
    # Sort by timestamp and print
    timeline.sort(key=lambda x: x[0])
    for ts, event in timeline:
        delta = ts - start_time
        print(f"  {ts.strftime('%H:%M:%S.%f')[:-3]} (+{delta.total_seconds():.2f}s): {event}")
    
    # Analyze message timing
    if len(client_messages) > 0 and len(server_messages) > 0:
        first_client_ts = min(e['timestamp'] for e in client_messages)
        first_server_ts = min(e['timestamp'] for e in server_messages)
        
        if first_server_ts > first_client_ts:
            response_time = (first_server_ts - first_client_ts).total_seconds()
            print(f"\nTime between first client message and first server response: {response_time:.2f} seconds")
            
            if response_time > 5:
                print("WARNING: Slow response time from server (> 5 seconds)")
        
        if audio_chunks:
            first_audio_ts = min(e['timestamp'] for e in audio_chunks)
            audio_delay = (first_audio_ts - first_client_ts).total_seconds()
            print(f"Time between first client message and first audio chunk: {audio_delay:.2f} seconds")
            
            if audio_delay > 10:
                print("WARNING: Very slow audio response time (> 10 seconds)")
    
    # Check for potential issues
    if not audio_chunks and len(server_messages) > 0:
        print("\nISSUE DETECTED: Server responded but no audio chunks were received")
        
        # Look for specific error messages
        auth_errors = [e for e in conn_events if 'json_data' in e and 
                      isinstance(e['json_data'], dict) and 
                      e['json_data'].get('type') == 'error' and 
                      'auth' in e['json_data'].get('message', '').lower()]
        
        if auth_errors:
            print("  Possible authentication issue:")
            for e in auth_errors:
                print(f"    {e['json_data'].get('message')}")
        
        rate_limit_errors = [e for e in conn_events if 'json_data' in e and 
                           isinstance(e['json_data'], dict) and 
                           e['json_data'].get('type') == 'error' and 
                           'rate limit' in e['json_data'].get('message', '').lower()]
        
        if rate_limit_errors:
            print("  Rate limit issue detected:")
            for e in rate_limit_errors:
                print(f"    {e['json_data'].get('message')}")
        
        model_errors = [e for e in conn_events if 'json_data' in e and 
                      isinstance(e['json_data'], dict) and 
                      e['json_data'].get('type') == 'error' and 
                      'model' in e['json_data'].get('message', '').lower()]
        
        if model_errors:
            print("  Model-related issue detected:")
            for e in model_errors:
                print(f"    {e['json_data'].get('message')}")


def main():
    parser = argparse.ArgumentParser(description="Analyze WebSocket proxy logs")
    parser.add_argument("log_file", help="Path to log file")
    parser.add_argument("--conn", help="Connection ID to analyze (default: all)")
    args = parser.parse_args()
    
    log_path = Path(args.log_file)
    if not log_path.exists():
        print(f"Log file not found: {log_path}")
        return
    
    print(f"Analyzing log file: {log_path}")
    events = parse_log_file(log_path)
    
    if not events:
        print("No events found in log file")
        return
    
    print(f"Found {len(events)} events")
    analyze_connection(events, args.conn)


if __name__ == "__main__":
    main() 