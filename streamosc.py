from flask import Flask, jsonify, render_template, request
from flask_socketio import SocketIO, emit, join_room, leave_room
from pythonosc import udp_client
import random
import time
import threading
import json
import uuid
import logging

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key'  # Change this to a secure secret key
socketio = SocketIO(app, cors_allowed_origins="*")

# Configure logging
logging.basicConfig(level=logging.WARNING)  # Set default level to WARNING
logger = logging.getLogger(__name__)

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
    log.setLevel(logging.WARNING)
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
MAX_QUEUE_SIZE = 100  # Maximum number of messages to queue per receiver

def send_random_osc_messages():
    clients = [udp_client.SimpleUDPClient(dest["ip"], dest["port"]) for dest in destinations]
    
    while is_sending:
        # Randomly select an OSC address from current_addresses
        address = random.choice(current_addresses)
        
        # Generate a random value (between 0 and 1)
        value = 1.0
        
        # Send the OSC message to all destinations
        for client in clients:
            client.send_message(address, value)
        
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

@app.route('/')
def index():
    return render_template('index.html', 
                         destinations=destinations,
                         addresses=current_addresses,
                         is_sending=is_sending,
                         interval_min=interval_min,
                         interval_max=interval_max)

@socketio.on('connect')
def handle_connect():
    """Handle new client connections"""
    try:
        connected_clients.add(request.sid)
        # Send initial state to the connecting client
        emit('status_update', {
            'is_sending': is_sending,
            'destinations': destinations,
            'addresses': current_addresses,
            'interval_min': interval_min,
            'interval_max': interval_max
        })
        
        # Send current receiver list
        emit('receiver_list_updated', {
            'receivers': get_receivers_list()
        })
        
        logger.info(f"New client connected (sid: {request.sid})")
    except Exception as e:
        logger.error(f"Error handling new connection: {e}")

@socketio.on('disconnect')
def handle_disconnect():
    """Handle client disconnection and cleanup"""
    try:
        # Remove from connected clients
        if request.sid in connected_clients:
            connected_clients.remove(request.sid)
        
        # Find and cleanup any registered receiver
        receiver_to_remove = None
        for receiver_id, info in registered_receivers.items():
            if info.get('socket_id') == request.sid:
                receiver_to_remove = receiver_id
                try:
                    leave_room(receiver_id)
                    logger.info(f"Receiver {info['name']} (ID: {receiver_id}) left room successfully")
                except Exception as e:
                    logger.error(f"Error leaving room for receiver {info['name']}: {e}")
                break
        
        # Update receiver status or remove if found
        if receiver_to_remove:
            # Mark as inactive instead of removing
            registered_receivers[receiver_to_remove]['active'] = False
            
            # Notify other clients about the status change
            try:
                emit('receiver_list_updated', {
                    'receivers': get_receivers_list()
                }, broadcast=True)
                logger.info(f"Receiver {registered_receivers[receiver_to_remove]['name']} marked as inactive")
            except Exception as e:
                logger.error(f"Failed to broadcast receiver status update: {e}")
                
    except Exception as e:
        logger.error(f"Error during disconnect handling: {e}")

@socketio.on('start_sending')
def handle_start_sending(data):
    global is_sending, send_thread, destinations, current_addresses, interval_min, interval_max
    
    if not is_sending:
        # Update configuration from the request
        new_destinations = data.get('destinations', [])
        new_addresses = data.get('addresses', [])
        new_interval_min = data.get('interval_min', interval_min)
        new_interval_max = data.get('interval_max', interval_max)
        
        if new_destinations:
            destinations = new_destinations
        if new_addresses:
            current_addresses = new_addresses
        if new_interval_min is not None:
            interval_min = float(new_interval_min)
        if new_interval_max is not None:
            interval_max = float(new_interval_max)
        
        is_sending = True
        send_thread = threading.Thread(target=send_random_osc_messages)
        send_thread.start()
        emit('status_update', {
            'status': 'started',
            'message': 'OSC message sending started',
            'is_sending': True
        }, broadcast=True)

@socketio.on('stop_sending')
def handle_stop_sending():
    global is_sending, send_thread
    
    if is_sending:
        is_sending = False
        if send_thread:
            send_thread.join()
        emit('status_update', {
            'status': 'stopped',
            'message': 'OSC message sending stopped',
            'is_sending': False
        }, broadcast=True)

# Relay service handlers
@socketio.on('register_receiver')
def handle_register_receiver(data):
    """Register a client as an OSC message receiver"""
    try:
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
        
        # Send confirmation to the receiver
        try:
            emit('registration_confirmed', {
                'receiver_id': receiver_id,
                'message': f'Successfully registered as "{receiver_name}"'
            })
        except Exception as e:
            logger.error(f"Failed to send registration confirmation to receiver {receiver_name}: {e}")
        
        return {'receiver_id': receiver_id}
        
    except Exception as e:
        logger.error(f"Failed to register receiver: {e}")
        emit('registration_error', {
            'message': 'Failed to register receiver'
        })
        return {'error': str(e)}

@socketio.on('unregister_receiver')
def handle_unregister_receiver(data):
    """Unregister a client as an OSC message receiver"""
    try:
        receiver_id = data.get('receiver_id')
        
        if receiver_id in registered_receivers:
            receiver_name = registered_receivers[receiver_id]['name']
            
            try:
                leave_room(receiver_id)
                logger.info(f"Receiver {receiver_name} (ID: {receiver_id}) left room successfully")
            except Exception as e:
                logger.error(f"Error leaving room for receiver {receiver_name}: {e}")
            
            del registered_receivers[receiver_id]
            if receiver_id in message_queue:
                del message_queue[receiver_id]
            
            # Notify all clients about the removed receiver
            try:
                emit('receiver_list_updated', {
                    'receivers': get_receivers_list()
                }, broadcast=True)
            except Exception as e:
                logger.error(f"Failed to broadcast receiver list update: {e}")
            
            return {'success': True, 'message': 'Receiver unregistered successfully'}
        
        return {'success': False, 'message': 'Receiver not found'}
        
    except Exception as e:
        logger.error(f"Error during receiver unregistration: {e}")
        return {'success': False, 'message': str(e)}

@socketio.on('request_receiver_list')
def handle_request_receiver_list():
    """Send the current list of registered receivers to the client"""
    emit('receiver_list_updated', {
        'receivers': get_receivers_list()
    })

def get_receivers_list():
    """Get a list of registered receivers for client display"""
    return [
        {
            'id': receiver_id,
            'name': info['name'],
            'active': info['active'],
            'created_at': info['created_at']
        }
        for receiver_id, info in registered_receivers.items()
    ]

@socketio.on('send_value')
def handle_send_value(data):
    """Handle manual message sending from the UI"""
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

@socketio.on('disconnect_receiver')
def handle_disconnect_receiver(data):
    """Manually disconnect a relay client"""
    try:
        receiver_id = data.get('receiver_id')
        
        if receiver_id in registered_receivers:
            receiver_info = registered_receivers[receiver_id]
            receiver_name = receiver_info['name']
            socket_id = receiver_info['socket_id']
            
            try:
                # Send manual disconnect event to the client
                emit('manual_disconnect', {
                    'message': 'Manually disconnected by server'
                }, room=socket_id)
                
                # Disconnect the client's socket
                socketio.close_room(receiver_id)
                logger.info(f"Manually disconnected receiver {receiver_name} (ID: {receiver_id})")
                
                # Mark as inactive
                registered_receivers[receiver_id]['active'] = False
                
                # Notify all clients about the status change
                emit('receiver_list_updated', {
                    'receivers': get_receivers_list()
                }, broadcast=True)
                
                return {'success': True, 'message': f'Successfully disconnected {receiver_name}'}
            except Exception as e:
                logger.error(f"Error disconnecting receiver {receiver_name}: {e}")
                return {'success': False, 'message': str(e)}
        else:
            return {'success': False, 'message': 'Receiver not found'}
            
    except Exception as e:
        logger.error(f"Error during manual receiver disconnect: {e}")
        return {'success': False, 'message': str(e)}

@socketio.on('toggle_verbose_mode')
def handle_toggle_verbose(data):
    """Handle verbose mode toggle from client"""
    enabled = data.get('enabled', False)
    set_verbose_mode(enabled)
    emit('verbose_mode_updated', {
        'enabled': enabled
    }, broadcast=True)

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=7401, debug=True)
