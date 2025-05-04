import asyncio
from simple_websocket_server import WebSocketServer, WebSocket
import json
import uuid
import logging
import os
import random
import time
import threading
from datetime import datetime
from http.server import HTTPServer, SimpleHTTPRequestHandler
import socket

# Configure logging
log_level = os.environ.get('LOG_LEVEL', 'INFO')
logging.basicConfig(level=getattr(logging, log_level), format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Log basic startup information
logger.info(f"Starting server process ID: {os.getpid()}")

# Default list of OSC addresses
OSC_ADDRESSES = [
    "/mass/tile1",
    "/mass/tile2",
    "/mass/tile3",
    "/mass/tile4",
    "/mass/tile5",
    "/mass/tile6",
    "/mass/tile7",
    "/mass/tile8",
    "/mass/tile9",
    "/mass/tile10",
    "/mass/tile11",
    "/mass/tile12",
    "/mass/tile13",
    "/mass/tile14",
]

# Global variables
is_sending = False
send_thread = None
current_addresses = OSC_ADDRESSES.copy()
interval_min = 0.5
interval_max = 3.0
connected_clients = set()
web_clients = set()

class WebHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory='templates', **kwargs)

    def do_GET(self):
        if self.path == '/':
            self.path = '/index.html'
        elif self.path == '/logs':
            self.path = '/logs.html'
        return super().do_GET()

class OSCServer(WebSocket):
    def handle(self):
        """Handle incoming messages"""
        global is_sending, send_thread
        try:
            data = json.loads(self.data)
            if data.get('type') == 'auth':
                # Simple authentication - just acknowledge
                self.send_message(json.dumps({
                    'type': 'auth_ok',
                    'message': 'Connected'
                }))
            elif data.get('type') == 'start_sending':
                if not is_sending:
                    is_sending = True
                    send_thread = threading.Thread(target=send_random_osc_messages)
                    send_thread.daemon = True
                    send_thread.start()
                    logger.info("Started sending OSC messages")
                    # Notify web clients
                    notify_web_clients({'type': 'status_update', 'is_sending': True})
            elif data.get('type') == 'stop_sending':
                is_sending = False
                logger.info("Stopped sending OSC messages")
                # Notify web clients
                notify_web_clients({'type': 'status_update', 'is_sending': False})
            elif data.get('type') == 'web_client':
                # Handle web client messages
                if data.get('action') == 'start':
                    if not is_sending:
                        is_sending = True
                        send_thread = threading.Thread(target=send_random_osc_messages)
                        send_thread.daemon = True
                        send_thread.start()
                        logger.info("Started sending OSC messages")
                        notify_web_clients({'type': 'status_update', 'is_sending': True})
                elif data.get('action') == 'stop':
                    is_sending = False
                    logger.info("Stopped sending OSC messages")
                    notify_web_clients({'type': 'status_update', 'is_sending': False})
        except Exception as e:
            logger.error(f"Error handling message: {e}")

    def connected(self):
        """Handle new connection"""
        global is_sending, send_thread
        logger.info(f"Client connected: {self.address}")
        connected_clients.add(self)
        if not is_sending:
            is_sending = True
            send_thread = threading.Thread(target=send_random_osc_messages)
            send_thread.daemon = True
            send_thread.start()
            logger.info("Started sending OSC messages")
            notify_web_clients({'type': 'status_update', 'is_sending': True})

    def handle_close(self):
        """Handle client disconnection"""
        global is_sending
        logger.info(f"Client disconnected: {self.address}")
        connected_clients.remove(self)
        if not connected_clients:
            is_sending = False
            logger.info("No clients connected, stopped sending messages")
            notify_web_clients({'type': 'status_update', 'is_sending': False})

def notify_web_clients(message):
    """Send a message to all web clients"""
    for client in web_clients:
        try:
            client.send_message(json.dumps(message))
        except Exception as e:
            logger.error(f"Error sending to web client: {e}")

def send_random_osc_messages():
    """Send random OSC messages to all connected clients"""
    logger.info(f"Starting OSC message sending to {len(connected_clients)} clients")
    
    while is_sending:
        try:
            # Randomly select an OSC address from current_addresses
            address = random.choice(current_addresses)
            value = random.uniform(0, 1)
            
            # Create message
            message = {
                'address': address,
                'value': value,
                'timestamp': time.time()
            }
            
            # Send to all connected clients
            if connected_clients:
                logger.info(f"[Server] Broadcasting: {address} = {value}")
                for client in connected_clients:
                    try:
                        client.send_message(json.dumps(message))
                    except Exception as e:
                        logger.error(f"Error sending to client {client.address}: {e}")
                
                # Also send to web clients for display
                notify_web_clients({
                    'type': 'osc_message',
                    'message': message
                })
            else:
                logger.warning("[Server] No clients connected")
                time.sleep(1)
                continue
            
            # Random delay between messages
            delay = random.uniform(interval_min, interval_max)
            time.sleep(delay)
            
        except Exception as e:
            logger.error(f"[Server] Error in send_random_osc_messages: {e}")
            time.sleep(1)  # Wait before retrying

def run_http_server():
    """Run the HTTP server in a separate thread"""
    http_server = HTTPServer(('127.0.0.1', 8080), WebHandler)
    http_server.serve_forever()

if __name__ == '__main__':
    http_host = '127.0.0.1'
    http_port = 8080
    ws_host = '127.0.0.1'
    ws_port = 8081
    
    # Start HTTP server in a separate thread
    http_thread = threading.Thread(target=run_http_server)
    http_thread.daemon = True
    http_thread.start()
    
    logger.info(f"Starting HTTP server on {http_host}:{http_port}")
    logger.info(f"Starting WebSocket server on {ws_host}:{ws_port}")
    server = WebSocketServer(ws_host, ws_port, OSCServer)
    server.serve_forever()


