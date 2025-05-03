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
import urllib.parse
import asyncio
import websockets
from pythonosc import udp_client
from pythonosc import osc_message_builder
from pythonosc import osc_bundle_builder
import uuid

# Load environment variables
load_dotenv()

# Default configuration
DEFAULT_SERVER_PORT = 7401
DEFAULT_SERVER_URL = 'https://massdev.one'  # Changed from localhost
DEFAULT_LOCAL_PORT = 57120
DEFAULT_API_KEY = os.environ.get('API_KEYS', 'default-key-for-development').split(',')[0]  # Take first key from comma-separated list

# Configuration file path
CONFIG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'config')
CONFIG_FILE = os.path.join(CONFIG_DIR, 'client_config.json')

# Ensure config directory exists
os.makedirs(CONFIG_DIR, exist_ok=True)

# Default configuration
DEFAULT_CONFIG = {
    'server_url': DEFAULT_SERVER_URL,  # This will now use https://massdev.one
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
                # Ensure server_url is correct
                if 'server_url' in config:
                    url = config['server_url']
                    if 'YOUR_SERVER_IP' in url:
                        config['server_url'] = 'https://massdev.one'  # Use the correct domain
                    elif not url.startswith(('http://', 'https://')):
                        config['server_url'] = 'https://' + url  # Ensure HTTPS
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

class OSCRelayClient:
    def __init__(self, server_url, api_key, osc_port=57120):
        self.server_url = server_url
        self.api_key = api_key
        self.osc_port = osc_port
        self.websocket = None
        self.connected = False
        self.receiver_id = None
        self.osc_client = udp_client.SimpleUDPClient("127.0.0.1", self.osc_port)
        self.message_queue = []
        self.is_sending = False
        self.send_thread = None

    async def connect(self):
        try:
            self.websocket = await websockets.connect(self.server_url)
            self.connected = True
            
            # Send authentication
            await self.websocket.send(json.dumps({
                'type': 'auth',
                'api_key': self.api_key
            }))
            
            # Start message handling
            asyncio.create_task(self.handle_messages())
            
            logger.info("Connected to server")
            return True
        except Exception as e:
            logger.error(f"Connection error: {e}")
            self.connected = False
            return False

    async def handle_messages(self):
        try:
            async for message in self.websocket:
                data = json.loads(message)
                
                if data['type'] == 'error':
                    logger.error(f"Server error: {data.get('message')}")
                    
                elif data['type'] == 'status':
                    logger.info(f"Status update: {data.get('message')}")
                    self.is_sending = data.get('is_sending', False)
                    
                elif data['type'] == 'registration_confirmed':
                    self.receiver_id = data.get('receiver_id')
                    logger.info(f"Registered as receiver: {self.receiver_id}")
                    
                elif data['type'] == 'osc':
                    address = data.get('address')
                    value = data.get('value')
                    if address and value is not None:
                        self.osc_client.send_message(address, value)
                        
                elif data['type'] == 'client_list_update':
                    logger.info(f"Connected clients: {data.get('clients', [])}")
                    
                elif data['type'] == 'receiver_list_update':
                    logger.info(f"Registered receivers: {data.get('receivers', [])}")
                    
        except Exception as e:
            logger.error(f"Message handling error: {e}")
            self.connected = False
            await self.reconnect()

    async def reconnect(self):
        while not self.connected:
            try:
                logger.info("Attempting to reconnect...")
                if await self.connect():
                    break
                await asyncio.sleep(5)
            except Exception as e:
                logger.error(f"Reconnection error: {e}")
                await asyncio.sleep(5)

    async def register_receiver(self, name="Unnamed Receiver"):
        if self.connected:
            await self.websocket.send(json.dumps({
                'type': 'register',
                'name': name
            }))

    async def send_osc_message(self, address, value):
        if self.connected:
            await self.websocket.send(json.dumps({
                'type': 'osc',
                'address': address,
                'value': value
            }))

    async def start_sending(self):
        if self.connected:
            await self.websocket.send(json.dumps({
                'type': 'start_sending'
            }))

    async def stop_sending(self):
        if self.connected:
            await self.websocket.send(json.dumps({
                'type': 'stop_sending'
            }))

    async def close(self):
        if self.websocket:
            await self.websocket.close()
        self.connected = False

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
            self.config = self.load_config()  # Load configuration from file
            self.restore_settings()
            self.setup_ui()

        def load_config(self):
            """Load configuration from file"""
            try:
                if os.path.exists(CONFIG_FILE):
                    with open(CONFIG_FILE, 'r') as f:
                        config = json.load(f)
                        # Ensure server_url is correct
                        if 'server_url' in config:
                            url = config['server_url']
                            if 'YOUR_SERVER_IP' in url:
                                config['server_url'] = 'https://massdev.one'
                            elif not url.startswith(('http://', 'https://')):
                                config['server_url'] = 'https://' + url
                        logger.info(f"Loaded config from file: {config}")
                        return config
            except Exception as e:
                logger.error(f"Error loading config: {e}")
            
            # Return default config if loading fails
            return {
                'server_url': 'https://massdev.one',
                'api_key': '',
                'receiver_name': 'default',
                'local_ip': '127.0.0.1',
                'local_port': 57120,
                'client_name': 'default'
            }

        def save_config(self):
            """Save configuration to file"""
            try:
                # Update config with current values
                self.config['server_url'] = self.server_url_input.text()
                self.config['api_key'] = self.api_key_input.text()
                self.config['client_name'] = self.name_input.text()
                self.config['local_ip'] = self.local_ip_input.text()
                self.config['local_port'] = int(self.local_port_input.text())
                
                # Ensure config directory exists
                os.makedirs(CONFIG_DIR, exist_ok=True)
                
                # Save to file
                with open(CONFIG_FILE, 'w') as f:
                    json.dump(self.config, f, indent=4)
                logger.info(f"Saved config to {CONFIG_FILE}")
                return True
            except Exception as e:
                logger.error(f"Error saving config: {e}")
                return False

        def setup_ui(self):
            layout = QVBoxLayout()

            # Server URL input with status indicator
            server_layout = QHBoxLayout()
            server_layout.addWidget(QLabel('Server URL:'))
            self.server_url_input = QLineEdit(self.config.get('server_url', 'https://massdev.one'))
            self.server_url_input.setToolTip("The URL of the OSC Relay Server")
            server_layout.addWidget(self.server_url_input)
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
            self.start_button = QPushButton("Start")
            self.start_button.setToolTip("Start receiving OSC messages")
            self.stop_button = QPushButton("Stop")
            self.stop_button.setToolTip("Stop receiving OSC messages")
            self.stop_button.setEnabled(False)
            btn_layout.addWidget(self.start_button)
            btn_layout.addWidget(self.stop_button)
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

            self.start_button.clicked.connect(self.start_client)
            self.stop_button.clicked.connect(self.stop_client)

        def restore_settings(self):
            geometry = self.settings.value('geometry')
            if geometry:
                self.setGeometry(geometry)

        def save_settings(self):
            self.settings.setValue('geometry', self.geometry())
            
            # Update config with current values
            self.config['server_url'] = self.server_url_input.text()
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
            """Start the OSC relay client"""
            try:
                # Save current configuration
                if not self.save_config():
                    self.status_label.setText("Error: Failed to save configuration")
                    return
                
                # Create client with current config
                self.client = OSCRelayClient(self.server_url_input.text(), self.api_key_input.text(), int(self.local_port_input.text()))
                
                # Connect signals
                self.client.status_signal.connect(self.update_status)
                self.client.message_signal.connect(self.add_message)
                
                # Start client
                self.client.start()
                
                # Update UI
                self.start_button.setEnabled(False)
                self.stop_button.setEnabled(True)
                self.server_url_input.setEnabled(False)
                self.api_key_input.setEnabled(False)
                self.name_input.setEnabled(False)
                self.local_ip_input.setEnabled(False)
                self.local_port_input.setEnabled(False)
                
            except Exception as e:
                logger.error(f"Error starting client: {e}")
                self.status_label.setText(f"Error: {str(e)}")
                # Reset UI if start failed
                self.start_button.setEnabled(True)
                self.stop_button.setEnabled(False)
                self.server_url_input.setEnabled(True)
                self.api_key_input.setEnabled(True)
                self.name_input.setEnabled(True)
                self.local_ip_input.setEnabled(True)
                self.local_port_input.setEnabled(True)

        def stop_client(self):
            """Stop the OSC relay client"""
            if self.client:
                try:
                    # Set manual disconnect flag
                    self.client.was_manually_disconnected = True
                    # Stop the client
                    self.client.stop()
                    # Wait for client to stop
                    if self.client.thread and self.client.thread.is_alive():
                        self.client.thread.join(timeout=5)
                    self.client = None
                except Exception as e:
                    logger.error(f"Error stopping client: {e}")
                    self.status_label.setText(f"Error stopping client: {str(e)}")
            
            # Reset UI
            self.start_button.setEnabled(True)
            self.stop_button.setEnabled(False)
            self.server_url_input.setEnabled(True)
            self.api_key_input.setEnabled(True)
            self.name_input.setEnabled(True)
            self.local_ip_input.setEnabled(True)
            self.local_port_input.setEnabled(True)
            self.status_label.setText('Status: Stopped')

        def test_api_key(self):
            """Test the API key"""
            api_key = self.api_key_input.text().strip() or DEFAULT_API_KEY
            server_url = self.server_url_input.text().strip()
            
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

    # Create config dictionary
    config = {
        'server_url': args.server or DEFAULT_SERVER_URL,
        'api_key': args.api_key or DEFAULT_API_KEY,
        'receiver_name': args.name or socket.gethostname(),
        'local_ip': args.local_ip or '127.0.0.1',
        'local_port': args.local_port or DEFAULT_LOCAL_PORT
    }

    # Save config to file
    config_path = os.path.join(CONFIG_DIR, 'client_config.json')
    try:
        with open(config_path, 'w') as f:
            json.dump(config, f, indent=4)
        logger.info(f"Saved config to {config_path}")
    except Exception as e:
        logger.error(f"Error saving config: {e}")
        sys.exit(1)

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
        client = OSCRelayClient(config['server_url'], config['api_key'], config['local_port'])
        client.status_signal.connect(lambda status: print(f"Status: {status}"))
        client.message_signal.connect(lambda msg: print(f"Message: {msg}"))
        asyncio.run(client.connect())
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            asyncio.run(client.close())
            print("Shutting down...")

if __name__ == "__main__":
    main() 