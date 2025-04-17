FROM python:3.9-slim

WORKDIR /app

# Install system dependencies for aiortc and PortAudio
RUN apt-get update && apt-get install -y \
    build-essential \
    libavdevice-dev \
    libavfilter-dev \
    libopus-dev \
    libvpx-dev \
    pkg-config \
    libsrtp2-dev \
    portaudio19-dev \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy server code
COPY audio_server.py .

# Create directories
RUN mkdir -p recordings
RUN mkdir -p logs

# Expose port for the server
EXPOSE 8000

# Command to run the server
CMD ["python", "audio_server.py"] 