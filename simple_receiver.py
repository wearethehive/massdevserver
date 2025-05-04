#!/usr/bin/env python3
"""
Simple OSC Message Receiver

This script connects to the OSC relay server and prints received messages to the console.
"""

import websocket
import json
import logging
import sys
from datetime import datetime

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Default configuration
DEFAULT_SERVER_URL = 'ws://localhost:8080'

class SimpleReceiver:
    def __init__(self, server_url):
        self.server_url = server_url
        self.ws = None

    def on_message(self, ws, message):
        """Handle incoming messages"""
        try:
            data = json.loads(message)
            if 'address' in data and 'value' in data:
                # Format timestamp if available
                timestamp = data.get('timestamp')
                if timestamp:
                    time_str = datetime.fromtimestamp(timestamp).strftime('%H:%M:%S.%f')
                else:
                    time_str = datetime.now().strftime('%H:%M:%S.%f')
                
                # Print message in a nice format
                print(f"[{time_str}] {data['address']} = {data['value']:.3f}")
            elif data.get('type') == 'auth_ok':
                logger.info(f"Connected to server: {data['message']}")
        except Exception as e:
            logger.error(f"Error processing message: {e}")

    def on_error(self, ws, error):
        """Handle errors"""
        logger.error(f"WebSocket error: {error}")

    def on_close(self, ws, close_status_code, close_msg):
        """Handle connection close"""
        logger.info("Disconnected from server")

    def on_open(self, ws):
        """Handle connection open"""
        logger.info("Connected to server")
        # Send simple auth message
        ws.send(json.dumps({
            'type': 'auth',
            'name': 'SimpleReceiver'
        }))

    def start(self):
        """Start the receiver and connect to the server"""
        try:
            logger.info(f"Connecting to {self.server_url}")
            websocket.enableTrace(True)
            self.ws = websocket.WebSocketApp(
                self.server_url,
                on_message=self.on_message,
                on_error=self.on_error,
                on_close=self.on_close,
                on_open=self.on_open
            )
            self.ws.run_forever()
        except Exception as e:
            logger.error(f"Error starting receiver: {e}")
            return False

    def stop(self):
        """Stop the receiver"""
        if self.ws:
            self.ws.close()

def main():
    # Get command line arguments
    import argparse
    parser = argparse.ArgumentParser(description='Simple OSC Message Receiver')
    parser.add_argument('--server', default=DEFAULT_SERVER_URL, help='Server URL')
    args = parser.parse_args()

    # Create and start receiver
    receiver = SimpleReceiver(args.server)
    
    try:
        receiver.start()
    except KeyboardInterrupt:
        logger.info("Shutting down...")
        receiver.stop()
        sys.exit(0)

if __name__ == "__main__":
    main() 