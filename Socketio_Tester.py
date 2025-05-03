import socketio
import logging

# Enable logging to see connection details
logging.basicConfig(level=logging.DEBUG)

# Replace with your server's public Socket.IO endpoint
SERVER_URL = "https://massdev.one"
API_KEY = "2d300078ba649e578967b679d1e0cbb76db78934"  # or read from env

# Create a Socket.IO client instance
sio = socketio.Client(
    logger=True,
    engineio_logger=True,
    ssl_verify=False,
)

# Optional: manually override headers (e.g., Origin)
sio.eio.headers = {
    'Origin': 'https://massdev.one',
    'Host': 'massdev.one',
    'X-Forwarded-Proto': 'https',
}

# Connection event handlers
@sio.event
def connect():
    print("[✓] Connected successfully.")
    sio.disconnect()

@sio.event
def connect_error(data):
    print("[!] Connection failed:", data)

@sio.event
def disconnect():
    print("[✗] Disconnected.")

try:
    print(f"Connecting to {SERVER_URL} ...")
    sio.connect(SERVER_URL, auth={'api_key': API_KEY}, wait_timeout=10)
except Exception as e:
    print("[!] Exception during connect:", e)
