import socketio
import logging
import time

# Configure logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Create Socket.IO client
sio = socketio.Client(reconnection=True, reconnection_attempts=5, reconnection_delay=1)

@sio.event
def connect():
    logger.info("Connected to server")
    logger.info(f"Connected namespaces: {sio.namespaces}")
    logger.info(f"Socket ID: {sio.sid}")
    # Send authentication message
    sio.emit('auth', {
        'api_key': '2d300078ba649e578967b679d1e0cbb76db78934',
        'name': 'test_client'
    })

@sio.event
def disconnect():
    logger.info("Disconnected from server")

@sio.event
def error(data):
    logger.error(f"Error: {data}")

@sio.event
def registration_confirmed(data):
    logger.info(f"Registration confirmed: {data}")
    logger.info(f"Current Socket ID: {sio.sid}")
    # Request receiver list
    sio.emit('request_receiver_list')

@sio.event
def status_update(data):
    logger.info(f"Status update: {data}")

@sio.on('osc', namespace='/')
def handle_osc(data):
    logger.info(f"Received OSC message: {data}")

def main():
    while True:
        try:
            if not sio.connected:
                # Connect to server with explicit namespace
                logger.info("Connecting to server...")
                sio.connect('http://127.0.0.1:8080', namespaces=['/'])
            
            # Keep the connection alive
            time.sleep(1)
            
        except KeyboardInterrupt:
            logger.info("Shutting down...")
            sio.disconnect()
            break
        except Exception as e:
            logger.error(f"Error: {e}")
            if sio.connected:
                sio.disconnect()
            time.sleep(1)  # Wait before retrying

if __name__ == "__main__":
    main() 