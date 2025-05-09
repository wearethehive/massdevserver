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
import websocket
from pythonosc import udp_client
from pythonosc import osc_message_builder
from pythonosc import osc_bundle_builder
import uuid
from pythonosc import osc_server
from pythonosc import dispatcher
from pathlib import Path
import traceback
from PySide6.QtCore import Qt, Signal, QObject, QSettings, QPoint, QSize

# Disable websocket debug logging BEFORE any websocket operations
websocket.enableTrace(False)
logging.getLogger('websocket').setLevel(logging.WARNING)
logging.getLogger('websocket-client').setLevel(logging.WARNING)
logging.getLogger('websocket._app').setLevel(logging.WARNING)
logging.getLogger('websocket._core').setLevel(logging.WARNING)
logging.getLogger('websocket._handshake').setLevel(logging.WARNING)
logging.getLogger('websocket._http').setLevel(logging.WARNING)
logging.getLogger('websocket._socket').setLevel(logging.WARNING)
logging.getLogger('websocket._url').setLevel(logging.WARNING)
logging.getLogger('websocket._utils').setLevel(logging.WARNING)

# Load environment variables
load_dotenv()

# Default configuration
DEFAULT_SERVER_PORT = 8080
DEFAULT_SERVER_URL = 'ws://localhost:8080'
DEFAULT_LOCAL_PORT = 57120

# Configuration file path
CONFIG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'config')
CONFIG_FILE = os.path.join(CONFIG_DIR, 'client_config.json')

# Ensure config directory exists
os.makedirs(CONFIG_DIR, exist_ok=True)

# Default configuration
DEFAULT_CONFIG = {
    'server_url': DEFAULT_SERVER_URL,
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
                        config['server_url'] = DEFAULT_SERVER_URL
                    elif not url.startswith(('ws://', 'wss://')):
                        url = 'ws://' + url
                        config['server_url'] = url
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

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(os.path.join(CONFIG_DIR, f'osc_relay_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log'))
    ]
)
logger = logging.getLogger(__name__)

class MessageSignal(QObject):
    """Signal class for thread-safe GUI updates"""
    message_received = Signal(str)
    status_updated = Signal(str, bool)

class OSCRelayClient:
    def __init__(self, server_url, osc_port=57120):
        self.config = load_config()
        self.server_url = server_url or self.config.get('server_url', DEFAULT_SERVER_URL)
        self.osc_port = osc_port or self.config.get('local_port', DEFAULT_LOCAL_PORT)
        self.local_ip = self.config.get('local_ip', '127.0.0.1')
        self.client_name = self.config.get('client_name', socket.gethostname())
        
        logger.debug(f"Client configuration: server_url={self.server_url}, local_ip={self.local_ip}, osc_port={self.osc_port}")
        
        self.ws = None
        self.connected = False
        self.osc_client = None
        self.was_manually_disconnected = False
        self.connection_monitor_thread = None
        self.message_signal = MessageSignal()
        self.should_reconnect = True
        self.reconnect_delay = 5

    def on_message(self, ws, message):
        """Handle incoming WebSocket messages."""
        try:
            data = json.loads(message)
            
            # Handle disconnect request
            if data.get('type') == 'disconnect_requested':
                logger.info(f"Received disconnect request from server: {data.get('message')}")
                self.should_reconnect = False
                ws.close()
                return

            # Handle auth response
            if data.get('type') == 'auth_ok':
                logger.info(f"Connected to server: {data.get('message')}")
                self.connected = True
                if hasattr(self, 'window') and self.window:
                    self.message_signal.status_updated.emit(f"Connected - {data.get('message')}", True)
                return

            # Handle OSC messages (both direct and wrapped)
            if data.get('type') == 'osc_message':
                # If message is wrapped in osc_message type
                message_data = data.get('message', data)
            else:
                # If message is direct
                message_data = data

            # Process OSC message if it has the required fields
            if 'address' in message_data and 'value' in message_data:
                try:
                    # Initialize OSC client if not already done
                    if not self.osc_client:
                        self.osc_client = udp_client.SimpleUDPClient(self.local_ip, self.osc_port)
                        logger.info(f"Initialized OSC client for {self.local_ip}:{self.osc_port}")
                    
                    # Send the OSC message
                    self.osc_client.send_message(message_data['address'], message_data['value'])
                    
                    # Format message with timestamp
                    timestamp = datetime.now().strftime('%H:%M:%S.%f')[:-3]
                    message_text = f"[{timestamp}] {message_data['address']} = {message_data['value']:.3f}"
                    
                    # Log to console
                    logger.info(message_text)
                    
                    # Update GUI if available
                    if hasattr(self, 'window') and self.window:
                        self.message_signal.message_received.emit(message_text)
                except Exception as e:
                    logger.error(f"Error sending OSC message: {e}")
        except Exception as e:
            logger.error(f"Error handling message: {e}")

    def on_error(self, ws, error):
        """Handle errors"""
        logger.error(f"WebSocket error: {error}")
        self.connected = False
        if hasattr(self, 'window') and self.window:
            self.message_signal.status_updated.emit(f"Error: {error}", False)

    def on_close(self, ws, close_status_code, close_msg):
        """Handle WebSocket connection close."""
        logger.info(f"WebSocket connection closed: {close_status_code} - {close_msg}")
        if self.should_reconnect:
            logger.info("Attempting to reconnect...")
            time.sleep(self.reconnect_delay)
            self.start()
        else:
            logger.info("Reconnection disabled - client was explicitly disconnected")

    def on_open(self, ws):
        """Handle connection open"""
        logger.info("Connected to server")
        # Send simple auth message
        ws.send(json.dumps({
            'type': 'auth',
            'name': self.client_name
        }))

    def start(self):
        """Start the WebSocket client."""
        try:
            self.should_reconnect = True  # Reset reconnection flag when starting
            websocket.enableTrace(False)
            
            # Initialize OSC client
            try:
                self.osc_client = udp_client.SimpleUDPClient(self.local_ip, self.osc_port)
                logger.info(f"Initialized OSC client for {self.local_ip}:{self.osc_port}")
            except Exception as e:
                logger.error(f"Failed to initialize OSC client: {e}")
                return False
            
            # Ensure the URL starts with ws:// or wss://
            if not self.server_url.startswith(('ws://', 'wss://')):
                self.server_url = f"ws://{self.server_url}"
            
            logger.info(f"Connecting to {self.server_url}")
            
            # Create WebSocket connection
            self.ws = websocket.WebSocketApp(
                self.server_url,
                on_open=self.on_open,
                on_message=self.on_message,
                on_error=self.on_error,
                on_close=self.on_close
            )
            
            # Start connection in a separate thread
            self.connection_thread = threading.Thread(target=self.ws.run_forever)
            self.connection_thread.daemon = True
            self.connection_thread.start()
            
            return True
        except Exception as e:
            logger.error(f"Error starting client: {e}")
            return False

    def _monitor_connection(self):
        """Monitor the connection and attempt to reconnect if needed"""
        while True:
            try:
                if not self.connected and not self.was_manually_disconnected:
                    logger.warning("Connection lost, attempting to reconnect...")
                    try:
                        self.ws.run_forever()
                    except Exception as e:
                        logger.error(f"Error during reconnection: {e}")
                time.sleep(1)
            except Exception as e:
                logger.error(f"Error in connection monitor: {e}")
                time.sleep(5)

    def stop(self):
        """Stop the client connection"""
        try:
            self.should_reconnect = False
            if self.ws:
                self.ws.close()
            self.connected = False
            
            # Clean up OSC client
            if self.osc_client:
                self.osc_client = None
            
            logger.info("Client stopped")
        except Exception as e:
            logger.error(f"Error stopping client: {e}")

# PySide6 GUI
try:
    from PySide6.QtWidgets import (QApplication, QWidget, QLabel, QLineEdit, QPushButton, 
                                 QTextEdit, QVBoxLayout, QHBoxLayout, QGridLayout, 
                                 QDialog, QDialogButtonBox, QStyle)
    from PySide6.QtGui import QColor, QPainter
    PySide6 = True
except ImportError:
    PySide6 = False

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
            self.config = self.load_config()
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
                                config['server_url'] = DEFAULT_SERVER_URL
                            elif not url.startswith(('ws://', 'wss://')):
                                url = 'ws://' + url
                                config['server_url'] = url
                        logger.info(f"Loaded config from file: {config}")
                        return config
            except Exception as e:
                logger.error(f"Error loading config: {e}")
            
            return {
                'server_url': DEFAULT_SERVER_URL,
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
            self.server_url_input = QLineEdit(self.config.get('server_url', DEFAULT_SERVER_URL))
            self.server_url_input.setToolTip("The URL of the OSC Relay Server")
            server_layout.addWidget(self.server_url_input)
            self.status_indicator = StatusIndicator()
            server_layout.addWidget(self.status_indicator)
            layout.addLayout(server_layout)

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
            self.save_config()

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
            """Update the status display in the GUI"""
            self.status_label.setText(f'Status: {status}')
            # Check for various connected states
            is_connected = any(state in status.lower() for state in [
                'connected', 
                'registered', 
                'running'
            ])
            self.status_indicator.set_status(is_connected)
            
            # Update button states based on connection status
            if 'connected' in status.lower():
                self.start_button.setEnabled(True)
                self.stop_button.setEnabled(False)
                self.server_url_input.setEnabled(False)
                self.name_input.setEnabled(False)
                self.local_ip_input.setEnabled(False)
                self.local_port_input.setEnabled(False)
            elif 'disconnected' in status.lower():
                self.start_button.setEnabled(True)
                self.stop_button.setEnabled(False)
                self.server_url_input.setEnabled(True)
                self.name_input.setEnabled(True)
                self.local_ip_input.setEnabled(True)
                self.local_port_input.setEnabled(True)

        def add_message(self, msg):
            """Add a message to the log"""
            try:
                logger.debug(f"[GUI] Received message to add: {msg}")
                timestamp = datetime.now().strftime("%H:%M:%S")
                formatted_msg = f"[{timestamp}] {msg}"
                logger.debug(f"[GUI] Formatted message: {formatted_msg}")
                
                # Use append to add text
                self.messages.append(formatted_msg)
                logger.debug(f"[GUI] Message appended to QTextEdit: {formatted_msg}")
                
                # Scroll to bottom
                self.messages.verticalScrollBar().setValue(
                    self.messages.verticalScrollBar().maximum()
                )
                logger.debug("[GUI] Scrolled to bottom of message panel")
                
            except Exception as e:
                error_msg = f"Error adding message to panel: {e}"
                logger.error(f"[GUI] {error_msg}")
                self.status_label.setText(error_msg)

        def show_about(self):
            dialog = AboutDialog(self)
            dialog.exec()

        def start_client(self):
            """Start the OSC relay client"""
            try:
                logger.info("[GUI] Starting client...")
                
                # Save current configuration
                if not self.save_config():
                    error_msg = "Error: Failed to save configuration"
                    logger.error(f"[GUI] {error_msg}")
                    self.status_label.setText(error_msg)
                    return
                
                # Create client with current config
                logger.info("[GUI] Creating OSCRelayClient instance")
                self.client = OSCRelayClient(
                    self.server_url_input.text(),
                    int(self.local_port_input.text())
                )
                
                # Pass window reference to client
                self.client.window = self
                
                # Connect signals
                self.client.message_signal.message_received.connect(self.handle_message)
                self.client.message_signal.status_updated.connect(self.handle_status)
                
                # Start client
                if not self.client.start():
                    raise Exception("Failed to start client")
                
                logger.info("[GUI] Client started successfully")
                
                # Update UI
                self.start_button.setEnabled(False)
                self.stop_button.setEnabled(True)
                self.server_url_input.setEnabled(False)
                self.name_input.setEnabled(False)
                self.local_ip_input.setEnabled(False)
                self.local_port_input.setEnabled(False)
                
            except Exception as e:
                error_msg = f"Error starting client: {e}"
                logger.error(f"[GUI] {error_msg}")
                self.status_label.setText(error_msg)
                # Reset UI if start failed
                self.start_button.setEnabled(True)
                self.stop_button.setEnabled(False)
                self.server_url_input.setEnabled(True)
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
                    
                except Exception as e:
                    logger.error(f"Error stopping client: {e}")
                    self.status_label.setText(f"Error stopping client: {str(e)}")
            
            # Reset UI
            self.start_button.setEnabled(True)
            self.stop_button.setEnabled(False)
            self.server_url_input.setEnabled(True)
            self.name_input.setEnabled(True)
            self.local_ip_input.setEnabled(True)
            self.local_port_input.setEnabled(True)
            self.status_label.setText('Status: Stopped')
            self.status_indicator.set_status(False)

        def handle_message(self, message):
            current_text = self.messages.toPlainText()
            if current_text:
                message = f"{current_text}\n{message}"
            self.messages.setPlainText(message)
            # Keep only last 100 messages
            lines = self.messages.toPlainText().split('\n')
            if len(lines) > 100:
                self.messages.setPlainText('\n'.join(lines[-100:]))

        def handle_status(self, status, is_connected):
            self.status_label.setText(f"Status: {status}")
            self.status_indicator.set_status(is_connected)

def main():
    parser = argparse.ArgumentParser(description='OSC Relay Client')
    parser.add_argument('--nogui', action='store_true', help='Run without GUI (CLI mode)')
    parser.add_argument('--server', help='WebSocket server URL')
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
        client = OSCRelayClient(
            server_url=config['server_url'],
            osc_port=config['local_port']
        )
        try:
            if not client.start():
                logger.error("Failed to start client")
                sys.exit(1)
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            client.stop()
            print("Shutting down...")

if __name__ == "__main__":
    main() 