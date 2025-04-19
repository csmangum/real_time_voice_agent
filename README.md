# WebRTC Streaming Demo with FastAPI

A simple FastAPI server that streams dummy data to clients using WebRTC.

## Requirements

- Python 3.8+
- Dependencies listed in requirements.txt

## Installation

1. Clone this repository
2. Install the requirements:

```powershell
pip install -r requirements.txt
```

## Running the Server

Start the FastAPI server:

```powershell
python server.py
```

This will start the server at http://localhost:8000

## Testing

There are two ways to test the WebRTC streaming:

### 1. Web Browser

Open http://localhost:8000 in your browser and click the "Start Streaming" button.

### 2. Python Client

Run the provided client script:

```powershell
python client.py
```

The client will connect to the server, receive the streaming data, and print it to the console.

## Customizing the Stream

To modify what data is being streamed, edit the `DummyTrack` class in `server.py`. Currently, it sends simple counter data, but you can implement more complex streaming data.

## Notes on WebRTC

WebRTC typically requires HTTPS in production environments, but for local development, HTTP works fine. For production deployment, consider setting up proper HTTPS certificates. 