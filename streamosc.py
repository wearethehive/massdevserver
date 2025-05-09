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
log_level = os.environ.get('LOG_LEVEL', 'INFO')  # Default to INFO
logging.basicConfig(level=getattr(logging, log_level), format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Set all other loggers to INFO level
logging.getLogger('simple_websocket_server').setLevel(logging.INFO)
logging.getLogger('websockets').setLevel(logging.INFO)
logging.getLogger('asyncio').setLevel(logging.INFO)

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
connected_clients = {}  # Store both client info and WebSocket object
web_clients = set()

class WebHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory='.', **kwargs)  # Changed to root directory

    def do_GET(self):
        if self.path == '/':
            self.path = '/templates/index.html'
        elif self.path == '/logs':
            self.path = '/templates/logs.html'
        elif self.path.startswith('/static/'):
            # Serve static files directly from root static directory
            self.path = self.path[1:]  # Remove leading slash
        return super().do_GET()

    def translate_path(self, path):
        """Override to handle template variables"""
        if path.endswith('.html'):
            try:
                # Read the template file with UTF-8 encoding
                with open(os.path.join('templates', os.path.basename(path)), 'r', encoding='utf-8') as f:
                    content = f.read()
                
                # Replace template variables
                content = content.replace('{{ interval_min }}', str(interval_min))
                content = content.replace('{{ interval_max }}', str(interval_max))
                
                # Create a temporary file with the processed content
                temp_path = os.path.join('templates', f'temp_{os.path.basename(path)}')
                with open(temp_path, 'w', encoding='utf-8') as f:
                    f.write(content)
                
                return temp_path
            except Exception as e:
                logger.error(f"Error processing template: {e}")
                # Fall back to original path if there's an error
                return super().translate_path(path)
        
        return super().translate_path(path)

class OSCServer(WebSocket):
    def handle(self):
        """Handle incoming messages"""
        global is_sending, send_thread
        try:
            data = json.loads(self.data)
            if data.get('type') == 'auth':
                # Simple authentication - just acknowledge
                client_id = str(uuid.uuid4())
                client_info = {
                    'id': client_id,
                    'name': data.get('name', 'Unknown'),
                    'address': self.address[0],
                    'connected_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                }
                connected_clients[client_id] = {
                    'info': client_info,
                    'ws': self  # Store the WebSocket object
                }
                self.send_message(json.dumps({
                    'type': 'auth_ok',
                    'client_id': client_id,
                    'message': 'Connected'
                }))
                # Notify web clients about new client
                notify_web_clients({
                    'type': 'client_connected',
                    'client': client_info
                })
            elif data.get('type') == 'web_client':
                # Handle web client messages
                if data.get('action') == 'identify':
                    web_clients.add(self)
                    # Send current client list
                    self.send_message(json.dumps({
                        'type': 'client_list',
                        'clients': [client['info'] for client in connected_clients.values()]
                    }))
                    # Send current addresses
                    self.send_message(json.dumps({
                        'type': 'address_list',
                        'addresses': current_addresses
                    }))
                    # Send interval values
                    self.send_message(json.dumps({
                        'type': 'interval_values',
                        'min': interval_min,
                        'max': interval_max
                    }))
                elif data.get('action') == 'disconnect_client':
                    client_id = data.get('client_id')
                    if client_id in connected_clients:
                        client = connected_clients[client_id]
                        try:
                            # Send a special message to tell the client not to reconnect
                            client['ws'].send_message(json.dumps({
                                'type': 'disconnect_requested',
                                'message': 'Disconnected by server'
                            }))
                            # Close the client's WebSocket connection
                            client['ws'].close()
                            # Remove from connected clients
                            del connected_clients[client_id]
                            # Notify web clients about disconnection
                            notify_web_clients({
                                'type': 'client_disconnected',
                                'client_id': client_id
                            })
                            logger.info(f"Disconnected client {client_id}")
                        except Exception as e:
                            logger.error(f"Error disconnecting client {client_id}: {e}")
                elif data.get('action') == 'start':
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
                elif data.get('action') == 'send_message':
                    # Handle test message from web client
                    address = data.get('address')
                    value = data.get('value')
                    if address and value is not None:
                        logger.info(f"[Server] Sending test message: {address} = {value}")
                        message = {
                            'address': address,
                            'value': value,
                            'timestamp': time.time()
                        }
                        # Send to all connected clients
                        for client_id, client in connected_clients.items():
                            try:
                                client['ws'].send_message(json.dumps(message))
                            except Exception as e:
                                logger.error(f"Error sending to client {client['info']['address']}: {e}")
                        # Also send to web clients for display
                        notify_web_clients({
                            'type': 'osc_message',
                            'message': message
                        })
                elif data.get('action') == 'add_address':
                    address = data.get('address')
                    if address and address not in current_addresses:
                        current_addresses.append(address)
                        notify_web_clients({
                            'type': 'address_list',
                            'addresses': current_addresses
                        })
                elif data.get('action') == 'remove_address':
                    address = data.get('address')
                    if address in current_addresses:
                        current_addresses.remove(address)
                        notify_web_clients({
                            'type': 'address_list',
                            'addresses': current_addresses
                        })
        except Exception as e:
            logger.error(f"Error handling message: {e}")

    def connected(self):
        """Handle new connection"""
        logger.info(f"Client connected: {self.address}")
        # Removed automatic message sending - now controlled by start/stop buttons only

    def handle_close(self):
        """Handle client disconnection"""
        global is_sending
        logger.info(f"Client disconnected: {self.address}")
        
        # Remove from web clients if it's a web client
        if self in web_clients:
            web_clients.remove(self)
            return

        # Find and remove the client from connected_clients
        client_id = None
        for cid, client in connected_clients.items():
            if client['info']['address'] == self.address[0]:
                client_id = cid
                break

        if client_id:
            del connected_clients[client_id]
            # Notify web clients about disconnection
            notify_web_clients({
                'type': 'client_disconnected',
                'client_id': client_id
            })

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
                for client_id, client in connected_clients.items():
                    try:
                        # Send the raw message without wrapping it in a type
                        client['ws'].send_message(json.dumps(message))
                    except Exception as e:
                        logger.error(f"Error sending to client {client['info']['address']}: {e}")
                
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