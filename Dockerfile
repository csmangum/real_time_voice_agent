FROM python:3.10-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Special case for opencv in slim images
RUN apt-get update && apt-get install -y \
    libgl1-mesa-glx \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Copy application code (will include .env if it exists)
COPY . .

# Expose the port
EXPOSE 8000

# Command to run the application
CMD ["python", "run.py"] 