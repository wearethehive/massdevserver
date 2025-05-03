import asyncio
import websockets
import json
import uuid
import logging
import os
from pythonosc import udp_client
import random
import time
import threading
from dotenv import load_dotenv
from datetime import datetime, timedelta

# Configure logging
log_level = os.environ.get('LOG_LEVEL', 'INFO')
logging.basicConfig(level=getattr(logging, log_level), format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Log basic startup information
logger.info(f"Starting server process ID: {os.getpid()}")

# Load environment variables
env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env')
load_dotenv(env_path)

# Check if the .env file exists
if os.path.exists(env_path):
    logger.info("Environment file loaded successfully")
else:
    logger.error(f"Environment file not found at: {env_path}")

# Log non-sensitive configuration
logger.info(f"Server configured with:")
logger.info(f"Host: {os.environ.get('HOST', '0.0.0.0')}")
logger.info(f"Port: {os.environ.get('PORT', '7401')}")
logger.info(f"Debug mode: {os.environ.get('DEBUG', 'False')}")
logger.info(f"Log level: {os.environ.get('LOG_LEVEL', 'INFO')}")

# Manually set the API_KEYS variable from the .env file
if os.path.exists(env_path):
    with open(env_path, 'r') as f:
        for line in f:
            if line.startswith('API_KEYS='):
                api_key = line.strip().split('=', 1)[1]
                os.environ['API_KEYS'] = api_key
                logger.info("API keys loaded successfully")
                break

# Create logs directory if it doesn't exist
log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'logs')
if not os.path.exists(log_dir):
    os.makedirs(log_dir, exist_ok=True)

log_file = os.path.join(log_dir, 'server.log')

# Configure file logging
file_handler = logging.FileHandler(log_file)
file_handler.setLevel(getattr(logging, log_level))
file_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
logger.addHandler(file_handler)

# Global variables
verbose_mode = False
background_tasks = []
is_sending = False
send_thread = None
destinations = [{"ip": "127.0.0.1", "port": 57120}]  # Default destination
current_addresses = OSC_ADDRESSES.copy()  # Working copy of addresses
interval_min = 0.5  # Default minimum interval
interval_max = 3.0  # Default maximum interval
connected_clients = set()
connection_tracker = {}  # Dictionary to track client connections

# Relay service variables
registered_receivers = {}  # Dictionary to store registered receivers
message_queue = {}  # Dictionary to store messages for offline receivers
MAX_QUEUE_SIZE = 100

# API keys for client authentication
API_KEYS = os.environ.get('API_KEYS', '').split(',')
if not API_KEYS or API_KEYS[0] == '':
    API_KEYS = ['default-key-for-development']
logger.info(f"Server API keys: {API_KEYS}")

# Cache the OSC clients to avoid recreating them
osc_clients_cache = {}

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

def get_osc_clients():
    """Get or create OSC clients for the current destinations"""
    cache_key = json.dumps(destinations, sort_keys=True)
    if cache_key not in osc_clients_cache:
        osc_clients_cache[cache_key] = [udp_client.SimpleUDPClient(dest["ip"], dest["port"]) for dest in destinations]
    return osc_clients_cache[cache_key]

def send_random_osc_messages():
    clients = get_osc_clients()
    logger.info(f"Created OSC clients for destinations: {destinations}")
    
    while is_sending:
        try:
            # Randomly select an OSC address from current_addresses
            address = random.choice(current_addresses)
            value = random.uniform(0, 1)
            
            # Send to all destinations
            for client in clients:
                client.send_message(address, value)
            
            # Random delay between messages
            delay = random.uniform(interval_min, interval_max)
            time.sleep(delay)
            
        except Exception as e:
            logger.error(f"Error in send_random_osc_messages: {e}")
            time.sleep(1)  # Wait before retrying

async def handle_websocket(websocket, path):
    """Handle WebSocket connections"""
    client_id = str(uuid.uuid4())
    connected_clients.add(client_id)
    connection_tracker[client_id] = {
        'last_seen': datetime.now(),
        'auth': None,
        'websocket': websocket  # Store the websocket in the tracker
    }
    
    try:
        logger.info(f"New connection attempt from client: {client_id}")
        
        # Wait for authentication message
        auth_message = await websocket.recv()
        auth_data = json.loads(auth_message)
        
        logger.info(f"Auth data received: {auth_data.get('api_key')}")
        
        # Validate API key
        if auth_data.get('api_key') not in API_KEYS:
            logger.warning(f"Rejected client {client_id} with bad API key")
            await websocket.send(json.dumps({
                'type': 'error',
                'message': 'Invalid API key'
            }))
            return
        
        # Update connection tracker
        connection_tracker[client_id]['auth'] = auth_data
        
        # Send initial status
        status = {
            'status': 'connected',
            'message': 'Connected to server',
            'is_sending': is_sending,
            'destinations': destinations,
            'addresses': current_addresses
        }
        await websocket.send(json.dumps({
            'type': 'status_update',
            'data': status
        }))
        
        # Broadcast client list update
        await broadcast_client_list()
        
        # Main message loop
        async for message in websocket:
            try:
                data = json.loads(message)
                message_type = data.get('type')
                
                if message_type == 'register_receiver':
                    # Handle receiver registration
                    receiver_id = data.get('receiver_id')
                    registered_receivers[receiver_id] = {
                        'client_id': client_id,
                        'last_seen': datetime.now()
                    }
                    await broadcast_receiver_list()
                    
                elif message_type == 'send_value':
                    # Handle OSC value sending
                    address = data.get('address')
                    value = data.get('value')
                    if address and value is not None:
                        clients = get_osc_clients()
                        for client in clients:
                            client.send_message(address, value)
                            
                elif message_type == 'start_sending':
                    # Handle start sending command
                    if not is_sending:
                        is_sending = True
                        send_thread = threading.Thread(target=send_random_osc_messages)
                        send_thread.daemon = True
                        send_thread.start()
                        await broadcast_status_update()
                        
                elif message_type == 'stop_sending':
                    # Handle stop sending command
                    is_sending = False
                    await broadcast_status_update()
                    
            except json.JSONDecodeError:
                logger.error(f"Invalid JSON received from client {client_id}")
            except Exception as e:
                logger.error(f"Error processing message from client {client_id}: {e}")
                
    except websockets.exceptions.ConnectionClosed:
        logger.info(f"Client disconnected: {client_id}")
    finally:
        connected_clients.remove(client_id)
        if client_id in connection_tracker:
            del connection_tracker[client_id]
        await broadcast_client_list()

async def broadcast_client_list():
    """Broadcast updated client list to all connected clients"""
    client_list = list(connected_clients)
    message = {
        'type': 'client_list_update',
        'data': {'clients': client_list}
    }
    await broadcast_message(message)

async def broadcast_receiver_list():
    """Broadcast updated receiver list to all connected clients"""
    receiver_list = list(registered_receivers.keys())
    message = {
        'type': 'receiver_list_update',
        'data': {'receivers': receiver_list}
    }
    await broadcast_message(message)

async def broadcast_status_update():
    """Broadcast status update to all connected clients"""
    status = {
        'status': 'connected',
        'message': 'Connected to server',
        'is_sending': is_sending,
        'destinations': destinations,
        'addresses': current_addresses
    }
    message = {
        'type': 'status_update',
        'data': status
    }
    await broadcast_message(message)

async def broadcast_message(message):
    """Broadcast a message to all connected clients"""
    message_str = json.dumps(message)
    for client_id in connected_clients.copy():
        try:
            websocket = connection_tracker[client_id].get('websocket')
            if websocket:
                await websocket.send(message_str)
        except Exception as e:
            logger.error(f"Error broadcasting to client {client_id}: {e}")

async def start_websocket_server():
    """Start the WebSocket server"""
    host = os.environ.get('HOST', '0.0.0.0')
    port = int(os.environ.get('PORT', '7401'))
    
    async with websockets.serve(handle_websocket, host, port):
        logger.info(f"WebSocket server started on {host}:{port}")
        await asyncio.Future()  # run forever

if __name__ == '__main__':
    asyncio.run(start_websocket_server())
