"""
Run script for starting the Real-Time Voice Agent server with optimal latency settings.

This script configures and starts the FastAPI server with optimized WebSocket settings
for minimal latency in real-time audio streaming between AudioCodes and OpenAI.

Usage:
    python run.py [--port PORT] [--host HOST]
"""

import argparse
import os
import sys
from pathlib import Path

import uvicorn

# Import constants from app (will also load environment variables)
sys.path.append(str(Path(__file__).parent))

from app.config.logging_config import configure_logging

# Configure logging
logger = configure_logging()


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Start the Real-Time Voice Agent server"
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.getenv("PORT", "8000")),
        help="Port to run the server on (default: 8000 or PORT env var)",
    )
    parser.add_argument(
        "--host",
        default=os.getenv("HOST", "0.0.0.0"),
        help="Host to bind the server to (default: 0.0.0.0 or HOST env var)",
    )
    parser.add_argument(
        "--log-level",
        default=os.getenv("LOG_LEVEL", "INFO"),
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Logging level (default: INFO or LOG_LEVEL env var)",
    )
    return parser.parse_args()


def main():
    """Main entry point for starting the server with optimized settings."""
    args = parse_args()

    # Verify OpenAI API key is set
    if not os.getenv("OPENAI_API_KEY"):
        logger.error("OPENAI_API_KEY environment variable not set")
        print("Error: OPENAI_API_KEY environment variable is required")
        print("Please set it using: $env:OPENAI_API_KEY = 'your-api-key'")
        sys.exit(1)

    # Log server configuration
    logger.info(f"Starting server on http://{args.host}:{args.port}")
    logger.info(f"Log level: {args.log_level}")
    logger.info(f"OpenAI API key configured: {bool(os.getenv('OPENAI_API_KEY'))}")

    # Configure uvicorn with optimized WebSocket settings for low latency
    uvicorn.run(
        "app.main:app",
        host=args.host,
        port=args.port,
        log_level=args.log_level.lower(),
        # Use HTTP/1.1 for lower overhead than HTTP/2
        http="h11",
        # Disable access logs for lower overhead, we have our own logging
        access_log=False,
        # Reload on code changes during development
        reload=os.getenv("ENV", "production").lower() == "development",
    )


if __name__ == "__main__":
    main()
