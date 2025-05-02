#!/usr/bin/env python3
"""
OSC Relay Client with PySide6 GUI

This script connects to an OSC relay service via WebSocket and receives OSC messages.
It can either forward these messages to a local OSC server or process them directly.

Usage:
    python osc_relay_client.py
    (GUI will launch)
"""

import json
import time
import argparse
import sys
import logging
from datetime import datetime
import os
import threading
import socket
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Default configuration
DEFAULT_SERVER_PORT = 7401
DEFAULT_SERVER_URL = f'http://localhost:{DEFAULT_SERVER_PORT}'
DEFAULT_LOCAL_PORT = 57120
DEFAULT_API_KEY = os.environ.get('API_KEYS', 'default-key-for-development').split(',')[0]  # Take first key from comma-separated list

# Configuration file path
CONFIG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'config')
CONFIG_FILE = os.path.join(CONFIG_DIR, 'client_config.json')

# Ensure config directory exists
os.makedirs(CONFIG_DIR, exist_ok=True)

# Default configuration
DEFAULT_CONFIG = {
    'server_url': DEFAULT_SERVER_URL,
    'api_key': DEFAULT_API_KEY,
    'client_name': socket.gethostname(),
    'local_ip': '127.0.0.1',
    'local_port': DEFAULT_LOCAL_PORT
}

def load_config():
    """Load configuration from file"""
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r') as f:
                config = json.load(f)
                # Ensure all required keys exist
                for key, value in DEFAULT_CONFIG.items():
                    if key not in config:
                        config[key] = value
                logger.info(f"Loaded config from file: {config}")
                return config
        except Exception as e:
            logger.error(f"Error loading config: {e}")
    logger.info(f"Using default config: {DEFAULT_CONFIG}")
    return DEFAULT_CONFIG.copy()

def save_config(config):
    """Save configuration to file"""
    try:
        with open(CONFIG_FILE, 'w') as f:
            json.dump(config, f, indent=4)
        logger.info(f"Saved config to file: {config}")
        return True
    except Exception as e:
        logger.error(f"Error saving config: {e}")
        return False

def test_api_key():
    """Test function to check the API key"""
    config = load_config()
    api_key = config.get('api_key', DEFAULT_API_KEY)
    logger.info(f"Current API key: {api_key}")
    logger.info(f"Default API key: {DEFAULT_API_KEY}")
    logger.info(f"Environment API key: {os.environ.get('API_KEYS', 'Not set')}")
    return api_key

# Check for required packages
try:
    import socketio
except ImportError:
    print("Error: python-socketio package is not installed.")
    print("Please install it with: pip install python-socketio")
    sys.exit(1)

try:
    import requests
except ImportError:
    print("Error: requests package is not installed.")
    print("Please install it with: pip install requests")
    sys.exit(1)

try:
    from pythonosc import udp_client
except ImportError:
    print("Error: python-osc package is not installed.")
    print("Please install it with: pip install python-osc")
    sys.exit(1)

# Try to import PySide6 for GUI
try:
    from PySide6.QtWidgets import (QApplication, QWidget, QLabel, QLineEdit, QPushButton, 
                                 QTextEdit, QVBoxLayout, QHBoxLayout, QGridLayout, 
                                 QDialog, QDialogButtonBox, QStyle)
    from PySide6.QtCore import Qt, Signal, QObject, QSettings, QPoint, QSize
    from PySide6.QtGui import QColor, QPainter
except ImportError:
    PySide6 = None
else:
    PySide6 = True

# Ensure logs directory exists
LOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'logs')
os.makedirs(LOG_DIR, exist_ok=True)
log_filename = os.path.join(LOG_DIR, f'osc_relay_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log')

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(log_filename)
    ]
)
logger = logging.getLogger(__name__)

class OSCRelayClient(QObject):
    status_signal = Signal(str)
    message_signal = Signal(str)

    def __init__(self, config_path='config.json'):
        """Initialize the OSC relay client"""
        self.config = self.load_config(config_path)
        self.sio = socketio.Client(
            reconnection=True,
            reconnection_attempts=5,
            reconnection_delay=1000,
            reconnection_delay_max=5000,
            logger=True,
            engineio_logger=True,
            handle_sigint=True
        )
        self.osc_sender = None
        self.osc_receiver = None
        self.connection_lock = threading.Lock()
        self.is_connected = False
        self.is_registered = False
        self.receiver_id = None
        self.receiver_name = self.config.get('receiver_name', 'Unnamed Receiver')
        self.api_key = self.config.get('api_key', '')
        self.server_url = self.config.get('server_url', 'http://localhost:7401')
        
        # Set up event handlers
        self.sio.on('connect', self.on_connect)
        self.sio.on('disconnect', self.on_disconnect)
        self.sio.on('registration_confirmed', self.on_registration_confirmed)
        self.sio.on('registration_failed', self.on_registration_failed)
        self.sio.on('status_update', self.on_status_update)
        self.sio.on('error', self.on_error)

    def safe_emit_status(self, message):
        """Safely emit status signal with thread safety"""
        try:
            with self.signal_lock:
                if self.running:  # Only emit if client is still running
                    self.status_signal.emit(message)
        except Exception as e:
            logger.error(f"Error emitting status signal: {e}")

    def safe_emit_message(self, message):
        """Safely emit message signal with thread safety"""
        try:
            with self.signal_lock:
                if self.running:  # Only emit if client is still running
                    self.message_signal.emit(message)
        except Exception as e:
            logger.error(f"Error emitting message signal: {e}")

    def start(self):
        """Start the client"""
        if not self.running:
            self.running = True
            self.thread = threading.Thread(target=self.run, daemon=True)
            self.thread.start()

    def stop(self):
        """Stop the client"""
        self.running = False
        try:
            if self.sio.connected:
                self.sio.disconnect()
        except Exception as e:
            logger.error(f"Error during disconnect: {e}")
        
        if self.was_manually_disconnected:
            self.safe_emit_status("Stopped (manually disconnected)")
        else:
            self.safe_emit_status("Stopped")

    def run(self):
        """Main client loop"""
        try:
            with self.connection_lock:
                if self.is_connecting:
                    logger.info("Connection attempt already in progress")
                    return
                self.is_connecting = True

            # Connect with API key in query parameters
            logger.info(f"Connecting to server {self.server_url} with API key: {self.api_key}")
            
            # Only include API key in auth if it's not empty
            auth_data = {}
            if self.api_key and self.api_key.strip():
                auth_data = {'api_key': self.api_key}
            
            logger.info(f"Auth data: {auth_data}")
            
            # Check if already connected before attempting to connect
            if not self.sio.connected:
                try:
                    self.sio.connect(self.server_url, auth=auth_data, wait_timeout=5)
                    logger.info(f"Connected to server: {self.server_url}")
                    self.safe_emit_status(f"Connected to {self.server_url}")
                    self.start_time = time.time()
                    self.reconnect_attempts = 0  # Reset reconnect attempts on successful connection
                except Exception as e:
                    logger.error(f"Failed to connect: {e}")
                    self.safe_emit_status(f"Failed to connect: {e}")
                    if self.running and not self.was_manually_disconnected:
                        self.reconnect_attempts += 1
                        if self.reconnect_attempts <= self.max_reconnect_attempts:
                            delay = min(self.reconnect_delay * (2 ** (self.reconnect_attempts - 1)), self.max_reconnect_delay)
                            logger.info(f"Reconnecting in {delay} seconds (attempt {self.reconnect_attempts}/{self.max_reconnect_attempts})")
                            self.safe_emit_status(f"Reconnecting in {delay} seconds (attempt {self.reconnect_attempts}/{self.max_reconnect_attempts})")
                            time.sleep(delay)
                            if self.running:
                                self.run()
                        else:
                            logger.error("Max reconnection attempts reached")
                            self.safe_emit_status("Max reconnection attempts reached. Please check your connection and try again.")
                            self.stop()
            else:
                logger.info("Already connected to server")
                self.safe_emit_status("Already connected to server")
            
            while self.running:
                time.sleep(0.1)
        except Exception as e:
            logger.error(f"Error in run loop: {e}")
            self.safe_emit_status(f"Error: {e}")
        finally:
            self.is_connecting = False
            if self.connection_lock.locked():
                self.connection_lock.release()
            self.safe_emit_status("Stopped")

    def on_connect(self):
        """Handle successful connection to server"""
        logger.info(f"Connected to server: {self.server_url}")
        self.connected = True
        
        # Register as a receiver after successful connection
        try:
            if self.sio.connected:
                logger.info("Registering as receiver...")
                self.sio.emit('register_receiver', {
                    'name': self.name,
                    'api_key': self.api_key
                })
                logger.info("Registration request sent")
            else:
                logger.warning("Cannot register: Socket not connected")
        except Exception as e:
            logger.error(f"Error during registration: {e}")
        finally:
            # Always release the lock in a finally block
            if self.connection_lock.locked():
                self.connection_lock.release()

    def on_disconnect(self):
        """Handle disconnection"""
        logger.warning("Disconnected from server")
        self.safe_emit_status("Disconnected from server")
        
        # Only attempt reconnection if not manually disconnected
        if self.running and not self.was_manually_disconnected:
            self.safe_emit_status("Disconnected from server. Reconnecting in 5s...")
            time.sleep(5)
            if self.running:
                self.run()
        elif self.was_manually_disconnected:
            self.safe_emit_status("Manually disconnected. Please restart the client to reconnect.")

    def on_registration_confirmed(self, data):
        """Handle successful registration confirmation"""
        try:
            self.receiver_id = data.get('receiver_id')
            if self.receiver_id:
                logger.info(f"Successfully registered as receiver with ID: {self.receiver_id}")
                # Join the receiver's room
                self.sio.emit('join', {'room': self.receiver_id})
                # Request current status
                self.sio.emit('get_status', {'api_key': self.api_key})
            else:
                logger.warning("Registration confirmed but no receiver ID received")
        except Exception as e:
            logger.error(f"Error in registration confirmation handler: {e}")

    def on_registration_failed(self, data):
        """Handle registration failure"""
        error_msg = data.get('error', 'Unknown error')
        logger.error(f"Registration failed: {error_msg}")
        logger.error(f"Registration data: {data}")
        self.safe_emit_status(f"Registration failed: {error_msg}")
        self.was_manually_disconnected = True
        self.stop()

    def on_status_update(self, data):
        """Handle status updates from server"""
        try:
            status = data.get('status', '')
            message = data.get('message', '')
            is_sending = data.get('is_sending', False)
            receivers = data.get('receivers', [])
            
            logger.info(f"Status update: {status} - {message}")
            logger.info(f"Receivers: {receivers}")
            logger.info(f"Is sending: {is_sending}")
            
            # Update sending state
            self.is_sending = is_sending
            
            # If we're connected but not registered, try to register
            if status == 'connected' and not self.receiver_id and self.sio.connected:
                logger.info("Connected but not registered, attempting registration...")
                self.sio.emit('register_receiver', {
                    'name': self.name,
                    'api_key': self.api_key
                })
        except Exception as e:
            logger.error(f"Error in status update handler: {e}")

    def on_error(self, data):
        """Handle errors from server"""
        error_msg = data.get('error', 'Unknown error')
        logger.error(f"Error: {error_msg}")
        self.safe_emit_status(f"Error: {error_msg}")

    def on_relay_message(self, message):
        """Handle incoming OSC messages"""
        self.message_count += 1
        msg = f"{message['address']} = {message['value']}"
        logger.debug(f"Received OSC message: {msg}")
        if self.osc_client:
            try:
                self.osc_client.send_message(message['address'], message['value'])
            except Exception as e:
                logger.error(f"Failed to forward message: {e}")
        self.safe_emit_message(msg)

    def on_manual_disconnect(self, data):
        """Handle manual disconnection from server"""
        logger.info("Received manual disconnect from server")
        self.safe_emit_status("Manually disconnected by server")
        self.was_manually_disconnected = True
        self.stop()

    def start_sending(self, destinations=None, addresses=None, interval_min=None, interval_max=None):
        """Start sending OSC messages"""
        if not self.sio.connected:
            logger.error("Cannot start sending: Not connected to server")
            self.safe_emit_status("Cannot start sending: Not connected to server")
            return
        
        if not self.receiver_id:
            logger.error("Cannot start sending: Not registered as receiver")
            self.safe_emit_status("Cannot start sending: Not registered as receiver")
            return
        
        data = {
            'api_key': self.api_key,
            'receiver_id': self.receiver_id
        }
        
        if destinations:
            data['destinations'] = destinations
        if addresses:
            data['addresses'] = addresses
        if interval_min is not None:
            data['interval_min'] = interval_min
        if interval_max is not None:
            data['interval_max'] = interval_max
        
        logger.info(f"Starting OSC message sending with data: {data}")
        self.sio.emit('start_sending', data)

# PySide6 GUI
if PySide6:
    class AboutDialog(QDialog):
        def __init__(self, parent=None):
            super().__init__(parent)
            self.setWindowTitle("About Mass OSC Relay Client")
            self.setup_ui()

        def setup_ui(self):
            layout = QVBoxLayout()

            # Info text
            info_text = """
            <h3>Mass OSC Relay Client</h3>
            <p>Version 0.1</p>
            <p>Created by Rich Porter<br>
            <a href="mailto:rich@wearethehive.com">rich@wearethehive.com</a></p>
            <p>Mass Experience</p>
            """
            info_label = QLabel(info_text)
            info_label.setTextFormat(Qt.RichText)
            info_label.setOpenExternalLinks(True)
            info_label.setAlignment(Qt.AlignCenter)
            layout.addWidget(info_label)

            # OK button
            button_box = QDialogButtonBox(QDialogButtonBox.Ok)
            button_box.accepted.connect(self.accept)
            layout.addWidget(button_box)

            self.setLayout(layout)

    class StatusIndicator(QWidget):
        def __init__(self, parent=None):
            super().__init__(parent)
            self.setFixedSize(12, 12)
            self._color = QColor("#dc3545")  # Red by default

        def set_status(self, is_connected):
            self._color = QColor("#198754") if is_connected else QColor("#dc3545")
            self.update()

        def paintEvent(self, event):
            painter = QPainter(self)
            painter.setRenderHint(QPainter.Antialiasing)
            painter.setBrush(self._color)
            painter.setPen(Qt.NoPen)
            painter.drawEllipse(self.rect())

    class RelayClientWindow(QWidget):
        def __init__(self):
            super().__init__()
            self.setWindowTitle('Mass OSC Relay Client')
            self.setMinimumWidth(600)
            self.client = None
            self.settings = QSettings('Mass Experience', 'OSC Relay Client')
            self.config = load_config()  # Load configuration from file
            self.restore_settings()
            self.setup_ui()

        def setup_ui(self):
            layout = QVBoxLayout()

            # Server URL input with status indicator
            server_layout = QHBoxLayout()
            server_layout.addWidget(QLabel('Server URL:'))
            self.server_input = QLineEdit(self.config.get('server_url', DEFAULT_SERVER_URL))
            self.server_input.setToolTip(f"The URL of the OSC Relay Server (default port: {DEFAULT_SERVER_PORT})")
            server_layout.addWidget(self.server_input)
            self.status_indicator = StatusIndicator()
            server_layout.addWidget(self.status_indicator)
            layout.addLayout(server_layout)

            # API Key input
            api_key_layout = QHBoxLayout()
            api_key_layout.addWidget(QLabel('API Key:'))
            self.api_key_input = QLineEdit(self.config.get('api_key', DEFAULT_API_KEY))
            self.api_key_input.setToolTip("API key for authentication with the server")
            self.api_key_input.setEchoMode(QLineEdit.Password)
            api_key_layout.addWidget(self.api_key_input)
            
            # Add Test API Key button
            test_api_btn = QPushButton("Test")
            test_api_btn.setToolTip("Test the API key")
            test_api_btn.clicked.connect(self.test_api_key)
            api_key_layout.addWidget(test_api_btn)
            
            layout.addLayout(api_key_layout)

            # Name input
            name_layout = QHBoxLayout()
            name_layout.addWidget(QLabel('Name:'))
            self.name_input = QLineEdit(self.config.get('client_name', socket.gethostname()))
            self.name_input.setToolTip("A unique name to identify this client in the relay service")
            name_layout.addWidget(self.name_input)
            layout.addLayout(name_layout)

            # Local OSC Device settings
            local_layout = QHBoxLayout()
            local_layout.addWidget(QLabel('Local OSC Device:'))
            self.local_ip_input = QLineEdit(self.config.get('local_ip', '127.0.0.1'))
            self.local_ip_input.setToolTip("IP address of the local device that will receive OSC messages")
            local_layout.addWidget(QLabel('IP:'))
            local_layout.addWidget(self.local_ip_input)
            self.local_port_input = QLineEdit(str(self.config.get('local_port', DEFAULT_LOCAL_PORT)))
            self.local_port_input.setToolTip("Port number of the local device that will receive OSC messages")
            local_layout.addWidget(QLabel('Port:'))
            local_layout.addWidget(self.local_port_input)
            
            # Add Test Connection button
            test_btn = QPushButton("Test")
            test_btn.setToolTip("Test the connection to the local OSC device")
            test_btn.clicked.connect(self.test_local_connection)
            local_layout.addWidget(test_btn)
            local_layout.addStretch()
            layout.addLayout(local_layout)

            # Add some spacing between sections
            layout.addSpacing(10)

            # Buttons
            btn_layout = QHBoxLayout()
            self.start_btn = QPushButton("Start")
            self.start_btn.setToolTip("Start receiving OSC messages")
            self.stop_btn = QPushButton("Stop")
            self.stop_btn.setToolTip("Stop receiving OSC messages")
            self.stop_btn.setEnabled(False)
            btn_layout.addWidget(self.start_btn)
            btn_layout.addWidget(self.stop_btn)
            layout.addLayout(btn_layout)

            # Status
            self.status_label = QLabel("Status: Ready")
            layout.addWidget(self.status_label)

            # Messages section header with info button
            messages_header = QHBoxLayout()
            messages_header.addWidget(QLabel("Recent Messages:"))
            info_btn = QPushButton("ℹ")
            info_btn.setStyleSheet("""
                QPushButton {
                    border: none;
                    padding: 5px;
                    font-size: 16px;
                    background: transparent;
                }
                QPushButton:hover {
                    background-color: palette(alternate-base);
                }
            """)
            info_btn.setToolTip("About Mass OSC Relay Client")
            info_btn.clicked.connect(self.show_about)
            messages_header.addStretch()
            
            # Add Clear Log button
            clear_btn = QPushButton("Clear")
            clear_btn.setToolTip("Clear the message log")
            clear_btn.clicked.connect(self.clear_log)
            messages_header.addWidget(clear_btn)
            messages_header.addWidget(info_btn)
            layout.addLayout(messages_header)

            # Messages
            self.messages = QTextEdit()
            self.messages.setReadOnly(True)
            layout.addWidget(self.messages)

            self.setLayout(layout)

            self.start_btn.clicked.connect(self.start_client)
            self.stop_btn.clicked.connect(self.stop_client)

        def restore_settings(self):
            geometry = self.settings.value('geometry')
            if geometry:
                self.setGeometry(geometry)

        def save_settings(self):
            self.settings.setValue('geometry', self.geometry())
            
            # Update config with current values
            self.config['server_url'] = self.server_input.text()
            self.config['api_key'] = self.api_key_input.text()
            self.config['client_name'] = self.name_input.text()
            self.config['local_ip'] = self.local_ip_input.text()
            self.config['local_port'] = int(self.local_port_input.text())
            
            # Save config to file
            save_config(self.config)

        def closeEvent(self, event):
            self.save_settings()
            super().closeEvent(event)

        def clear_log(self):
            self.messages.clear()

        def test_local_connection(self):
            try:
                ip = self.local_ip_input.text()
                port = int(self.local_port_input.text())
                test_client = udp_client.SimpleUDPClient(ip, port)
                test_client.send_message("/test", 1)
                self.status_label.setText("Status: Test message sent successfully")
            except Exception as e:
                self.status_label.setText(f"Status: Test failed - {str(e)}")

        def update_status(self, status):
            self.status_label.setText(f'Status: {status}')
            # Check for various connected states
            is_connected = any(state in status.lower() for state in [
                'connected', 
                'registered', 
                'running'
            ])
            self.status_indicator.set_status(is_connected)

        def add_message(self, msg):
            timestamp = datetime.now().strftime("%H:%M:%S")
            self.messages.append(f"[{timestamp}] {msg}")

        def show_about(self):
            dialog = AboutDialog(self)
            dialog.exec()

        def start_client(self):
            server_url = self.server_input.text().strip()
            api_key = self.api_key_input.text().strip() or DEFAULT_API_KEY
            name = self.name_input.text().strip() or 'OSC Relay Client'
            local_ip = self.local_ip_input.text().strip()
            local_port = self.local_port_input.text().strip()

            logger.info(f"Starting client with server_url: {server_url}")
            logger.info(f"API key: {api_key}")
            logger.info(f"Name: {name}")
            logger.info(f"Local IP: {local_ip}")
            logger.info(f"Local Port: {local_port}")

            if not server_url.startswith('http://') and not server_url.startswith('https://'):
                server_url = 'http://' + server_url

            try:
                local_port_int = int(local_port)
            except ValueError:
                self.status_label.setText('Status: Invalid OSC port')
                return

            self.client = OSCRelayClient(server_url, local_ip, local_port_int, name, api_key)
            self.client.status_signal.connect(self.update_status)
            self.client.message_signal.connect(self.add_message)
            self.client.start()
            self.start_btn.setEnabled(False)
            self.stop_btn.setEnabled(True)
            self.status_label.setText('Status: Starting...')

        def stop_client(self):
            if self.client:
                self.client.stop()
                self.client = None
            self.start_btn.setEnabled(True)
            self.stop_btn.setEnabled(False)
            self.status_label.setText('Status: Stopped')

        def test_api_key(self):
            """Test the API key"""
            api_key = self.api_key_input.text().strip() or DEFAULT_API_KEY
            server_url = self.server_input.text().strip()
            
            if not server_url.startswith('http://') and not server_url.startswith('https://'):
                server_url = 'http://' + server_url
            
            # Test the API key by making a request to the server
            try:
                test_url = f"{server_url}/api/test_keys"
                logger.info(f"Testing API key by making a request to {test_url}")
                
                # First, check what API keys the server has
                response = requests.get(test_url)
                if response.status_code == 200:
                    server_keys = response.json()
                    logger.info(f"Server API keys: {server_keys}")
                    self.status_label.setText(f"Server API keys: {server_keys}")
                else:
                    logger.error(f"Failed to get server API keys: {response.status_code}")
                    self.status_label.setText(f"Failed to get server API keys: {response.status_code}")
                
                # Now test the API key
                test_url = f"{server_url}/api/status?api_key={api_key}"
                logger.info(f"Testing API key by making a request to {test_url}")
                response = requests.get(test_url)
                
                if response.status_code == 200:
                    logger.info(f"API key is valid for HTTP: {api_key}")
                    self.status_label.setText(f"API key is valid for HTTP: {api_key}")
                else:
                    logger.error(f"API key is invalid for HTTP: {api_key}, status code: {response.status_code}")
                    self.status_label.setText(f"API key is invalid for HTTP: {api_key}, status code: {response.status_code}")
                
                # Test socket.io connection
                self.test_socket_connection(server_url, api_key)
            except Exception as e:
                logger.error(f"Error testing API key: {e}")
                self.status_label.setText(f"Error testing API key: {e}")
        
        def test_socket_connection(self, server_url, api_key):
            """Test socket.io connection with API key"""
            try:
                sio = socketio.Client()
                
                # Set up event handlers
                @sio.event
                def connect():
                    logger.info("Socket.io connected successfully")
                    self.status_label.setText("Socket.io connected successfully")
                    sio.disconnect()
                
                @sio.event
                def connect_error(data):
                    logger.error(f"Socket.io connection error: {data}")
                    self.status_label.setText(f"Socket.io connection error: {data}")
                
                # Connect with API key
                auth_data = {}
                if api_key and api_key.strip():
                    auth_data = {'api_key': api_key}
                
                logger.info(f"Testing socket.io connection with auth data: {auth_data}")
                sio.connect(server_url, auth=auth_data)
                
                # Wait for connection or error
                time.sleep(2)
                
                if sio.connected:
                    logger.info("Socket.io connection test successful")
                    self.status_label.setText("Socket.io connection test successful")
                else:
                    logger.error("Socket.io connection test failed")
                    self.status_label.setText("Socket.io connection test failed")
            except Exception as e:
                logger.error(f"Error testing socket.io connection: {e}")
                self.status_label.setText(f"Error testing socket.io connection: {e}")

def main():
    parser = argparse.ArgumentParser(description='OSC Relay Client')
    parser.add_argument('--nogui', action='store_true', help='Run without GUI (CLI mode)')
    parser.add_argument('--server', help='WebSocket server URL')
    parser.add_argument('--api-key', help='API key for authentication')
    parser.add_argument('--local-ip', help='Local OSC server IP to forward messages to')
    parser.add_argument('--local-port', type=int, help='Local OSC server port to forward messages to')
    parser.add_argument('--name', help='Receiver name')
    parser.add_argument('--debug', action='store_true', help='Enable debug logging')
    args = parser.parse_args()

    if args.debug:
        logger.setLevel(logging.DEBUG)

    # Load configuration
    config = load_config()
    
    # Override config with command line arguments if provided
    if args.server:
        config['server_url'] = args.server
    if args.api_key:
        config['api_key'] = args.api_key
    if args.local_ip:
        config['local_ip'] = args.local_ip
    if args.local_port:
        config['local_port'] = args.local_port
    if args.name:
        config['client_name'] = args.name

    if not args.nogui:
        if not PySide6:
            print("Error: PySide6 is not installed. Please install it with: pip install PySide6")
            sys.exit(1)
        app = QApplication(sys.argv)
        window = RelayClientWindow()
        window.show()
        sys.exit(app.exec())
    else:
        # CLI mode
        if (config['local_ip'] is None and config['local_port'] is not None) or \
           (config['local_ip'] is not None and config['local_port'] is None):
            logger.error("Both --local-ip and --local-port must be specified for forwarding")
            sys.exit(1)
        client = OSCRelayClient(
            config['server_url'], 
            config['local_ip'], 
            config['local_port'], 
            config['client_name'],
            config['api_key']
        )
        client.status_signal.connect(lambda status: print(f"Status: {status}"))
        client.message_signal.connect(lambda msg: print(f"Message: {msg}"))
        client.start()
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            client.stop()
            print("Shutting down...")

if __name__ == "__main__":
    main() 