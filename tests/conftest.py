import asyncio
import os
import pytest
from fastapi.testclient import TestClient
from aiortc import RTCPeerConnection, RTCSessionDescription
import sys

# Add the parent directory to sys.path to import the server module
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from server import app

@pytest.fixture
def test_client():
    """
    Create a test client for FastAPI app
    """
    # Use direct instantiation instead of subclassing
    client = TestClient(app)
    return client

@pytest.fixture
def event_loop():
    """
    Create an instance of the default event loop for each test case
    """
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()

@pytest.fixture
def rtc_peer_connection():
    """
    Create a WebRTC peer connection for testing
    """
    pc = RTCPeerConnection()
    yield pc
    # Clean up - we need to run this in the event loop
    asyncio.get_event_loop().run_until_complete(pc.close())

@pytest.fixture
def mock_offer_sdp():
    """
    Return a mock SDP offer for testing
    """
    return """v=0
o=- 1596742744269 1 IN IP4 127.0.0.1
s=-
t=0 0
a=group:BUNDLE 0
a=msid-semantic: WMS ARDAMS
m=audio 9 UDP/TLS/RTP/SAVPF 111
c=IN IP4 0.0.0.0
a=rtcp:9 IN IP4 0.0.0.0
a=ice-ufrag:someufrag
a=ice-pwd:someicepwd
a=ice-options:trickle
a=fingerprint:sha-256 00:11:22:33:44:55:66:77:88:99:AA:BB:CC:DD:EE:FF:00:11:22:33:44:55:66:77:88:99:AA:BB:CC:DD:EE:FF
a=setup:actpass
a=mid:0
a=extmap:1 urn:ietf:params:rtp-hdrext:ssrc-audio-level
a=recvonly
a=rtcp-mux
a=rtpmap:111 opus/48000/2
a=fmtp:111 minptime=10;useinbandfec=1
""" 