from flask import Flask, jsonify, render_template, request
from flask_socketio import SocketIO, emit, join_room, leave_room
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_caching import Cache
from dotenv import load_dotenv
import os, uuid, time, logging
from datetime import datetime
from collections import deque

# Init Flask app
app = Flask(__name__, static_url_path='', static_folder='static', template_folder='templates')
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'secret!')

# Init cache and limiter
cache = Cache(app, config={'CACHE_TYPE': 'simple'})
limiter = Limiter(get_remote_address, app=app, default_limits=["200 per day", "50 per hour"])

# Init SocketIO
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='eventlet')

# Load env
load_dotenv()
API_KEYS = os.getenv("API_KEYS", "default-key-for-development").split(',')

# Globals
connected_clients = set()
connection_tracker = {}
registered_receivers = {}
destinations = []
current_addresses = []
is_sending = False
send_thread = None
message_queue = deque(maxlen=100)

# Logger setup
logger = logging.getLogger()
logging.basicConfig(level=logging.INFO)

# Helpers
def get_receivers_list():
    return [{
        'id': rid,
        'name': info['name'],
        'connected_at': info['connected_at']
    } for rid, info in registered_receivers.items()]

@app.route('/')
def index():
    try:
        logger.info("Serving index.html")
        path = os.path.abspath(os.path.join(app.template_folder, 'index.html'))
        logger.info(f"Resolved index.html path: {path}")
        return render_template('index.html', api_key=API_KEYS[0])
    except Exception as e:
        logger.exception("Failed to render index.html")
        return "Internal Server Error", 500

@socketio.on('connect')
def handle_connect(auth):
    client_id = request.sid
    logger.info(f"New client: {client_id}, auth: {auth}")
    if not auth or auth.get('api_key') not in API_KEYS:
        logger.warning(f"Rejected client {client_id} with bad API key")
        return False
    connected_clients.add(client_id)
    connection_tracker[client_id] = {'connected_at': datetime.now().isoformat()}
    logger.info(f"Accepted client {client_id}")
    emit('status_update', {
        'status': 'connected',
        'message': 'Connected to server',
        'is_sending': is_sending,
        'destinations': destinations,
        'addresses': current_addresses,
        'receivers': get_receivers_list()
    }, room=client_id)
    socketio.emit('receiver_list_update', {'receivers': get_receivers_list()}, broadcast=True)

@socketio.on('disconnect')
def handle_disconnect():
    client_id = request.sid
    logger.info(f"Client disconnected: {client_id}")
    connected_clients.discard(client_id)
    connection_tracker.pop(client_id, None)
    to_remove = [rid for rid, r in registered_receivers.items() if r['socket_id'] == client_id]
    for rid in to_remove:
        registered_receivers.pop(rid)
    socketio.emit('receiver_list_update', {'receivers': get_receivers_list()}, broadcast=True)

@socketio.on('register_receiver')
@limiter.limit("10 per minute")
def handle_register_receiver(data):
    client_id = request.sid
    name = data.get('name', 'Unnamed Receiver')
    api_key = data.get('api_key')
    if api_key not in API_KEYS:
        emit('registration_failed', {'error': 'Invalid API key'}, room=client_id)
        return
    if client_id not in connection_tracker:
        emit('registration_failed', {'error': 'Connection lost'}, room=client_id)
        return
    receiver_id = str(uuid.uuid4())
    registered_receivers[receiver_id] = {
        'name': name,
        'client_id': client_id,
        'api_key': api_key,
        'connected_at': connection_tracker[client_id]['connected_at'],
        'active': True,
        'socket_id': client_id
    }
    join_room(receiver_id)
    emit('registration_confirmed', {'receiver_id': receiver_id}, room=client_id)
    socketio.emit('receiver_list_update', {'receivers': get_receivers_list()}, broadcast=True)

@socketio.on('unregister_receiver')
@limiter.limit("10 per minute")
def handle_unregister_receiver(data):
    api_key = data.get('api_key')
    receiver_id = data.get('receiver_id')
    if api_key not in API_KEYS:
        emit('unregistration_failed', {'error': 'Unauthorized'})
        return
    if receiver_id not in registered_receivers:
        emit('unregistration_failed', {'error': 'Invalid receiver ID'})
        return
    registered_receivers.pop(receiver_id)
    leave_room(receiver_id)
    emit('unregistration_confirmed', {'message': 'Unregistered'})
    socketio.emit('receiver_list_update', {'receivers': get_receivers_list()}, broadcast=True)

@socketio.on('update_config')
def handle_update_config(data):
    global destinations, current_addresses
    destinations = data.get('destinations', [])
    current_addresses = data.get('addresses', [])
    emit('config_updated', {'message': 'Configuration updated'})

@socketio.on('queue_message')
def handle_queue_message(data):
    message_queue.append(data)

@socketio.on('start_sending')
def handle_start_sending():
    global is_sending, send_thread
    is_sending = True
    if not send_thread:
        send_thread = socketio.start_background_task(target=relay_messages)
    emit('sending_status', {'status': 'started'})

@socketio.on('stop_sending')
def handle_stop_sending():
    global is_sending
    is_sending = False
    emit('sending_status', {'status': 'stopped'})

def relay_messages():
    global is_sending
    while is_sending:
        if message_queue:
            message = message_queue.popleft()
            for receiver_id in registered_receivers:
                socketio.emit('osc_message', message, room=receiver_id)
        socketio.sleep(0.01)

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=7401)
