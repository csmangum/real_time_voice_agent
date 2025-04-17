# Real-Time Audio Server

A FastAPI server with aiortc for receiving real-time audio from clients.

## Features

- WebRTC audio streaming
- Audio recording to WAV files
- Simple API for client connection/disconnection
- Comprehensive logging for troubleshooting connection issues

## Deployment with Docker

### Prerequisites

- Docker and Docker Compose installed

### Steps to Deploy

1. Clone this repository

2. Build and start the Docker container:
   ```bash
   docker-compose up -d
   ```

3. The server will be available at http://localhost:8000

4. To stop the server:
   ```bash
   docker-compose down
   ```

## API Endpoints

- `GET /`: Server status check
- `POST /offer`: Send WebRTC offer to establish connection
- `POST /disconnect`: Disconnect a client

## Audio Files and Logs

Recorded audio files are stored in the `recordings` directory and mapped to the host system via Docker volume.

Detailed logs are available in the `logs` directory with timestamps for troubleshooting connection issues. Each server session creates a new log file with format `audio_server_YYYYMMDD_HHMMSS.log`.

## Troubleshooting

If you encounter connection issues:

1. Check the logs in the `logs` directory for detailed error messages
2. Common WebRTC issues include:
   - ICE connection failures (check network/firewall settings)
   - Codec compatibility issues
   - Audio format mismatches

The logs include details about:
- Connection state changes
- Audio format detection
- Frame processing errors
- Server startup and shutdown events 