FROM python:3.9-slim

WORKDIR /app

# Install system dependencies required for aiortc
RUN apt-get update && apt-get install -y \
    libavdevice-dev \
    libavfilter-dev \
    libopus-dev \
    libvpx-dev \
    pkg-config \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Create directories for logs and recordings
RUN mkdir -p logs server_recordings static

# Copy server code and static files
COPY server.py .
COPY static/ static/

# Expose the port the app runs on
EXPOSE 8000

# Define volumes for logs and recordings
VOLUME ["/app/logs", "/app/server_recordings"]

# Command to run the application
CMD ["python", "server.py"] 