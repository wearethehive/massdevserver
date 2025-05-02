from flask import Flask, jsonify, render_template, request, session
from flask_socketio import SocketIO, emit, join_room, leave_room
from pythonosc import udp_client
import random
import time
import threading
import json
import uuid
import logging
import os
from functools import wraps
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from dotenv import load_dotenv
import sys
from datetime import datetime
from flask_caching import Cache

# Configure logging - reduce logging overhead in production
log_level = os.environ.get('LOG_LEVEL', 'WARNING')
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

# Log the environment variables
logger.info("Environment configuration loaded")

# Check if API_KEYS is set in the system environment
if 'API_KEYS' in os.environ:
    logger.info("API keys configured")
else:
    logger.warning("No API keys configured")

app = Flask(__name__)
# Use environment variable for secret key
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'your-secret-key')

# Configure caching
cache_config = {
    'CACHE_TYPE': 'simple',
    'CACHE_DEFAULT_TIMEOUT': 300
}
app.config.from_mapping(cache_config)
cache = Cache(app)

# Configure CORS to only allow specific origins
allowed_origins = os.environ.get('ALLOWED_ORIGINS', 'http://localhost:7401').split(',')
socketio = SocketIO(app, cors_allowed_origins=allowed_origins, async_mode='threading', ping_timeout=60, ping_interval=25)

# Configure rate limiting
limiter = Limiter(
    app=app,
    key_func=get_remote_address,
    default_limits=["200 per day", "50 per hour"]
)

# Create logs directory if it doesn't exist
log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'logs')
if not os.path.exists(log_dir):
    os.makedirs(log_dir, exist_ok=True)

log_file = os.path.join(log_dir, 'server.log')

# Configure file logging only if needed
if log_level == 'DEBUG':
    file_handler = logging.FileHandler(log_file)
    file_handler.setLevel(logging.DEBUG)
    logger.addHandler(file_handler)

# Configure all relevant transport loggers
transport_loggers = [
    'engineio',
    'engineio.client',
    'socketio',
    'socketio.client',
    'socketio.server',
    'werkzeug',
    'websockets.client',
    'websockets.server'
]

for logger_name in transport_loggers:
    log = logging.getLogger(logger_name)
    log.setLevel(getattr(logging, log_level))
    log.propagate = False  # Prevent propagation to root logger

# Global variables
verbose_mode = False  # Add verbose mode flag

def set_verbose_mode(enabled):
    """Toggle verbose logging mode"""
    global verbose_mode
    verbose_mode = enabled
    level = logging.INFO if enabled else logging.WARNING
    
    # Update all transport loggers
    for logger_name in transport_loggers:
        logging.getLogger(logger_name).setLevel(level)
    
    # Update main logger
    logger.setLevel(level)

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
destinations = [{"ip": "127.0.0.1", "port": 57120}]  # Default destination
current_addresses = OSC_ADDRESSES.copy()  # Working copy of addresses
interval_min = 0.5  # Default minimum interval
interval_max = 3.0  # Default maximum interval
connected_clients = set()

# Relay service variables
registered_receivers = {}  # Dictionary to store registered receivers
message_queue = {}  # Dictionary to store messages for offline receivers
MAX_QUEUE_SIZE = 100

# API keys for client authentication
API_KEYS = os.environ.get('API_KEYS', '').split(',')
if not API_KEYS or API_KEYS[0] == '':
    API_KEYS = ['default-key-for-development']
logger.info(f"Server API keys: {API_KEYS}")

def require_api_key(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        api_key = request.args.get('api_key') or request.json.get('api_key')
        
        # If no API key is provided, use the default key
        if not api_key:
            api_key = 'default-key-for-development'
            logger.debug("Using default API key")
        
        if api_key not in API_KEYS:
            logger.warning(f"Unauthorized access attempt from {request.remote_addr}")
            return jsonify({"error": "Unauthorized"}), 401
        return f(*args, **kwargs)
    return decorated_function

# Cache the OSC clients to avoid recreating them
osc_clients_cache = {}

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
            
            # Generate a random value (between 0 and 1)
            value = 1.0
            
            # Send the OSC message to all destinations
            for client in clients:
                client.send_message(address, value)
                if verbose_mode:
                    logger.debug(f"Sent OSC message to {client._address}:{client._port} - {address}: {value}")
            
            # Notify connected clients about the message
            message_data = {
                'address': address,
                'value': value,
                'timestamp': time.time()
            }
            socketio.emit('osc_message', message_data)
            
            # Also send to registered relay receivers
            for receiver_id, receiver_info in registered_receivers.items():
                if receiver_info.get('active', False):
                    # Send directly to active receivers using their socket_id
                    socketio.emit('relay_message', message_data, room=receiver_info['socket_id'])
                else:
                    # Queue message for offline receivers
                    if receiver_id not in message_queue:
                        message_queue[receiver_id] = []
                    
                    # Add message to queue, maintaining max size
                    message_queue[receiver_id].append(message_data)
                    if len(message_queue[receiver_id]) > MAX_QUEUE_SIZE:
                        message_queue[receiver_id].pop(0)  # Remove oldest message
            
            # Random delay between interval_min and interval_max seconds
            time.sleep(random.uniform(interval_min, interval_max))
        except Exception as e:
            logger.error(f"Error in OSC message sending: {e}")
            time.sleep(1)  # Wait a bit before retrying

@app.route('/')
def index():
    # Get the first API key for the client
    api_key = API_KEYS[0] if API_KEYS else 'default-key-for-development'
    
    return render_template('index.html', 
                          destinations=destinations,
                          is_sending=is_sending,
                          addresses=current_addresses,
                          interval_min=interval_min,
                          interval_max=interval_max,
                          api_key=api_key)

@app.route('/api/status')
@limiter.limit("10 per minute")
@require_api_key
@cache.cached(timeout=5)  # Cache for 5 seconds
def get_status():
    return jsonify({
        'is_sending': is_sending,
        'destinations': destinations,
        'addresses': current_addresses,
        'interval_min': interval_min,
        'interval_max': interval_max,
        'connected_clients': len(connected_clients),
        'registered_receivers': len(registered_receivers)
    })

@app.route('/api/receivers')
@limiter.limit("10 per minute")
@require_api_key
@cache.cached(timeout=5)  # Cache for 5 seconds
def get_receivers():
    return jsonify({
        'receivers': get_receivers_list()
    })

def get_receivers_list():
    """Get a list of all registered receivers"""
    receivers = []
    for receiver_id, info in registered_receivers.items():
        receivers.append({
            'id': receiver_id,
            'name': info.get('name', 'Unnamed'),
            'active': info.get('active', False),
            'created_at': info.get('created_at', 0)
        })
    return receivers

@socketio.on('connect')
def handle_connect():
    """Handle client connection"""
    client_id = request.sid
    connected_clients.add(client_id)
    logger.info(f"Client connected: {client_id}")
    logger.info(f"Total connected clients: {len(connected_clients)}")
    emit('status_update', {
        'status': 'connected',
        'message': 'Connected to server',
        'is_sending': is_sending
    }, broadcast=True)

@socketio.on('disconnect')
def handle_disconnect():
    """Handle client disconnection"""
    client_id = request.sid
    if client_id in connected_clients:
        connected_clients.remove(client_id)
    logger.info(f"Client disconnected: {client_id}")
    logger.info(f"Total connected clients: {len(connected_clients)}")
    
    # Check if this client was a registered receiver
    for receiver_id, info in list(registered_receivers.items()):
        if info.get('socket_id') == client_id:
            # Mark receiver as inactive
            registered_receivers[receiver_id]['active'] = False
            logger.info(f"Receiver {info.get('name')} (ID: {receiver_id}) marked as inactive")
            
            # Notify all clients about the updated receiver list
            try:
                emit('receiver_list_updated', {
                    'receivers': get_receivers_list()
                }, broadcast=True)
            except Exception as e:
                logger.error(f"Failed to broadcast receiver list update: {e}")

@socketio.on('start_sending')
@limiter.limit("5 per minute")
def handle_start_sending(data):
    global is_sending, send_thread, destinations, current_addresses, interval_min, interval_max
    
    # Validate API key
    api_key = data.get('api_key')
    if not api_key or api_key not in API_KEYS:
        logger.warning("Unauthorized attempt to start sending")
        emit('status_update', {
            'status': 'error',
            'message': 'Unauthorized',
            'is_sending': is_sending
        })
        return
    
    if not is_sending:
        logger.info("Starting OSC message sending")
        # Update configuration from the request
        new_destinations = data.get('destinations', [])
        new_addresses = data.get('addresses', [])
        new_interval_min = data.get('interval_min', interval_min)
        new_interval_max = data.get('interval_max', interval_max)
        
        if new_destinations:
            destinations = new_destinations
            logger.info(f"Updated destinations: {destinations}")
        if new_addresses:
            current_addresses = new_addresses
            logger.info(f"Updated addresses: {current_addresses}")
        if new_interval_min is not None:
            interval_min = float(new_interval_min)
            logger.info(f"Updated interval_min: {interval_min}")
        if new_interval_max is not None:
            interval_max = float(new_interval_max)
            logger.info(f"Updated interval_max: {interval_max}")
        
        is_sending = True
        send_thread = threading.Thread(target=send_random_osc_messages)
        send_thread.start()
        logger.info("OSC message sending thread started")
        emit('status_update', {
            'status': 'started',
            'message': 'OSC message sending started',
            'is_sending': True
        }, broadcast=True)
    else:
        logger.info("OSC message sending already in progress")

@socketio.on('stop_sending')
@limiter.limit("5 per minute")
def handle_stop_sending(data):
    global is_sending, send_thread
    
    # Validate API key
    api_key = data.get('api_key')
    if not api_key or api_key not in API_KEYS:
        logger.warning("Unauthorized attempt to stop sending")
        emit('status_update', {
            'status': 'error',
            'message': 'Unauthorized',
            'is_sending': is_sending
        })
        return
    
    if is_sending:
        logger.info("Stopping OSC message sending")
        is_sending = False
        if send_thread:
            send_thread.join()
            logger.info("OSC message sending thread stopped")
        emit('status_update', {
            'status': 'stopped',
            'message': 'OSC message sending stopped',
            'is_sending': False
        }, broadcast=True)
    else:
        logger.info("OSC message sending already stopped")

# Relay service handlers
@socketio.on('register_receiver')
@limiter.limit("10 per minute")
def handle_register_receiver(data):
    """Register a client as an OSC message receiver"""
    try:
        # Validate API key
        api_key = data.get('api_key')
        logger.info(f"Registration attempt with API key: {api_key}")
        
        # If no API key is provided, use the default key
        if not api_key:
            api_key = 'default-key-for-development'
            logger.info(f"No API key provided for registration, using default: {api_key}")
        
        if api_key not in API_KEYS:
            logger.warning(f"Registration failed: Unauthorized (API key: {api_key})")
            emit('registration_failed', {
                'error': 'Unauthorized'
            })
            return
        
        receiver_name = data.get('name', 'Unnamed Receiver')
        receiver_id = str(uuid.uuid4())
        
        registered_receivers[receiver_id] = {
            'name': receiver_name,
            'socket_id': request.sid,
            'active': True,
            'created_at': time.time()
        }
        
        # Notify all clients about the new receiver immediately
        try:
            emit('receiver_list_updated', {
                'receivers': get_receivers_list()
            }, broadcast=True)
        except Exception as e:
            logger.error(f"Failed to broadcast receiver list update: {e}")
        
        # Join the socket to the receiver's room
        try:
            join_room(receiver_id)
            logger.info(f"Receiver {receiver_name} (ID: {receiver_id}) joined room successfully")
        except Exception as e:
            logger.error(f"Failed to join room for receiver {receiver_name}: {e}")
            # Clean up the registration if room joining fails
            if receiver_id in registered_receivers:
                del registered_receivers[receiver_id]
            raise
        
        # Send queued messages if any
        if receiver_id in message_queue and message_queue[receiver_id]:
            try:
                for message in message_queue[receiver_id]:
                    emit('relay_message', message, room=request.sid)
                # Clear queue after sending
                message_queue[receiver_id] = []
            except Exception as e:
                logger.error(f"Failed to send queued messages to receiver {receiver_name}: {e}")
        
        # Send confirmation to the client
        emit('registration_confirmed', {
            'receiver_id': receiver_id,
            'message': f'Successfully registered as {receiver_name}'
        })
        
    except Exception as e:
        logger.error(f"Error registering receiver: {e}")
        emit('registration_failed', {
            'error': str(e)
        })

@socketio.on('unregister_receiver')
@limiter.limit("10 per minute")
def handle_unregister_receiver(data):
    """Unregister a client as an OSC message receiver"""
    try:
        # Validate API key
        api_key = data.get('api_key')
        if not api_key or api_key not in API_KEYS:
            emit('unregistration_failed', {
                'error': 'Unauthorized'
            })
            return
        
        receiver_id = data.get('receiver_id')
        if not receiver_id or receiver_id not in registered_receivers:
            emit('unregistration_failed', {
                'error': 'Invalid receiver ID'
            })
            return
        
        # Remove the receiver
        del registered_receivers[receiver_id]
        
        # Leave the room
        leave_room(receiver_id)
        
        # Notify all clients about the updated receiver list
        emit('receiver_list_updated', {
            'receivers': get_receivers_list()
        }, broadcast=True)
        
        # Send confirmation to the client
        emit('unregistration_confirmed', {
            'message': 'Successfully unregistered'
        })
        
    except Exception as e:
        logger.error(f"Error unregistering receiver: {e}")
        emit('unregistration_failed', {
            'error': str(e)
        })

@socketio.on('send_value')
@limiter.limit("30 per minute")
def handle_send_value(data):
    """Handle manual message sending from the UI"""
    # Validate API key
    api_key = data.get('api_key')
    if not api_key or api_key not in API_KEYS:
        emit('send_failed', {
            'error': 'Unauthorized'
        })
        return
    
    address = data.get('address')
    value = data.get('value', 1.0)
    
    # Create OSC clients for all destinations
    clients = [udp_client.SimpleUDPClient(dest["ip"], dest["port"]) for dest in destinations]
    
    # Send the OSC message to all destinations
    for client in clients:
        client.send_message(address, value)
    
    # Prepare message data
    message_data = {
        'address': address,
        'value': value,
        'timestamp': time.time()
    }
    
    # Notify all connected clients about the message
    socketio.emit('osc_message', message_data)
    
    # Send to registered relay receivers
    for receiver_id, receiver_info in registered_receivers.items():
        if receiver_info.get('active', False):
            socketio.emit('relay_message', message_data, room=receiver_info['socket_id'])
        else:
            if receiver_id not in message_queue:
                message_queue[receiver_id] = []
            message_queue[receiver_id].append(message_data)
            if len(message_queue[receiver_id]) > MAX_QUEUE_SIZE:
                message_queue[receiver_id].pop(0)

@socketio.on('toggle_verbose_mode')
def handle_toggle_verbose(data):
    """Handle verbose mode toggle from client"""
    enabled = data.get('enabled', False)
    set_verbose_mode(enabled)
    emit('verbose_mode_updated', {
        'enabled': enabled
    }, broadcast=True)

@app.route('/api/test_keys')
def test_keys():
    """Test endpoint to check API keys"""
    return jsonify({
        'status': 'ok',
        'message': 'API keys are configured'
    })

if __name__ == '__main__':
    # Use environment variables for host and port
    host = os.environ.get('HOST', '0.0.0.0')
    port = int(os.environ.get('PORT', 7401))
    debug = os.environ.get('DEBUG', 'False').lower() == 'true'
    
    # Start the server without SSL (SSL will be handled by Nginx Proxy Manager)
    socketio.run(app, host=host, port=port, debug=debug, use_reloader=False)
