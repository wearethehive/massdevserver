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

# Default configuration
DEFAULT_SERVER_PORT = 80
DEFAULT_SERVER_URL = f'http://localhost:{DEFAULT_SERVER_PORT}'
DEFAULT_LOCAL_PORT = 57120

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

    def __init__(self, server_url, local_osc_ip=None, local_osc_port=None, name="OSC Relay Client"):
        super().__init__()
        self.server_url = server_url
        self.local_osc_ip = local_osc_ip
        self.local_osc_port = local_osc_port
        self.name = name
        self.receiver_id = None
        self.osc_client = None
        self.was_manually_disconnected = False
        if local_osc_ip and local_osc_port:
            try:
                self.osc_client = udp_client.SimpleUDPClient(local_osc_ip, local_osc_port)
                logger.info(f"Created OSC client for forwarding to {local_osc_ip}:{local_osc_port}")
            except Exception as e:
                logger.error(f"Failed to create OSC client: {e}")
                self.status_signal.emit(f"Failed to create OSC client: {e}")
        self.sio = socketio.Client()
        self.sio.on('connect', self.on_connect)
        self.sio.on('disconnect', self.on_disconnect)
        self.sio.on('registration_confirmed', self.on_registration_confirmed)
        self.sio.on('relay_message', self.on_relay_message)
        self.sio.on('manual_disconnect', self.on_manual_disconnect)
        self.message_count = 0
        self.start_time = None
        self.running = False
        self.thread = None

    def start(self):
        if not self.running:
            self.running = True
            self.thread = threading.Thread(target=self.run, daemon=True)
            self.thread.start()

    def stop(self):
        self.running = False
        try:
            if self.sio.connected:
                self.sio.disconnect()
        except Exception:
            pass
        if self.was_manually_disconnected:
            self.status_signal.emit("Stopped (manually disconnected)")
        else:
            self.status_signal.emit("Stopped")

    def run(self):
        try:
            self.sio.connect(self.server_url)
            logger.info(f"Connected to server: {self.server_url}")
            self.status_signal.emit(f"Connected to {self.server_url}")
            self.start_time = time.time()
            while self.running:
                time.sleep(0.1)
        except Exception as e:
            logger.error(f"Failed to connect: {e}")
            self.status_signal.emit(f"Failed to connect: {e}")
        finally:
            self.status_signal.emit("Stopped")

    def on_connect(self):
        logger.info("Connected to server, registering as receiver...")
        self.status_signal.emit("Connected, registering as receiver...")
        self.sio.emit('register_receiver', {'name': self.name})

    def on_disconnect(self):
        """Handle disconnection"""
        logger.warning("Disconnected from server")
        self.status_signal.emit("Disconnected from server")
        
        # Only attempt reconnection if not manually disconnected
        if self.running and not self.was_manually_disconnected:
            self.status_signal.emit("Disconnected from server. Reconnecting in 5s...")
            time.sleep(5)
            if self.running:
                self.run()
        elif self.was_manually_disconnected:
            self.status_signal.emit("Manually disconnected. Please restart the client to reconnect.")

    def on_registration_confirmed(self, data):
        self.receiver_id = data['receiver_id']
        logger.info(f"Registered as receiver: {self.name} (ID: {self.receiver_id})")
        self.status_signal.emit(f"Registered as receiver: {self.name}")

    def on_relay_message(self, message):
        self.message_count += 1
        msg = f"{message['address']} = {message['value']}"
        logger.debug(f"Received OSC message: {msg}")
        if self.osc_client:
            try:
                self.osc_client.send_message(message['address'], message['value'])
            except Exception as e:
                logger.error(f"Failed to forward message: {e}")
        self.message_signal.emit(msg)

    def on_manual_disconnect(self, data):
        """Handle manual disconnection from server"""
        logger.info("Received manual disconnect from server")
        self.status_signal.emit("Manually disconnected by server")
        self.was_manually_disconnected = True
        self.stop()

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
            self.restore_settings()
            self.setup_ui()

        def setup_ui(self):
            layout = QVBoxLayout()

            # Server URL input with status indicator
            server_layout = QHBoxLayout()
            server_layout.addWidget(QLabel('Dev Server URL:'))
            self.server_input = QLineEdit(self.settings.value('server_url', DEFAULT_SERVER_URL))
            self.server_input.setToolTip(f"The URL of the Mass Development Server (default port: {DEFAULT_SERVER_PORT})")
            server_layout.addWidget(self.server_input)
            self.status_indicator = StatusIndicator()
            server_layout.addWidget(self.status_indicator)
            layout.addLayout(server_layout)

            # Name input
            name_layout = QHBoxLayout()
            name_layout.addWidget(QLabel('Name:'))
            self.name_input = QLineEdit(self.settings.value('client_name', socket.gethostname()))
            self.name_input.setToolTip("A unique name to identify this client in the relay service")
            name_layout.addWidget(self.name_input)
            layout.addLayout(name_layout)

            # Local OSC Device settings
            local_layout = QHBoxLayout()
            local_layout.addWidget(QLabel('Local OSC Device:'))
            self.local_ip_input = QLineEdit(self.settings.value('local_ip', '127.0.0.1'))
            self.local_ip_input.setToolTip("IP address of the local device that will receive OSC messages")
            local_layout.addWidget(QLabel('IP:'))
            local_layout.addWidget(self.local_ip_input)
            self.local_port_input = QLineEdit(self.settings.value('local_port', str(DEFAULT_LOCAL_PORT)))
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
            self.settings.setValue('server_url', self.server_input.text())
            self.settings.setValue('client_name', self.name_input.text())
            self.settings.setValue('local_ip', self.local_ip_input.text())
            self.settings.setValue('local_port', self.local_port_input.text())

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
            name = self.name_input.text().strip() or 'OSC Relay Client'
            local_ip = self.local_ip_input.text().strip()
            local_port = self.local_port_input.text().strip()

            if not server_url.startswith('http://') and not server_url.startswith('https://'):
                server_url = 'http://' + server_url

            try:
                local_port_int = int(local_port)
            except ValueError:
                self.status_label.setText('Status: Invalid OSC port')
                return

            self.client = OSCRelayClient(server_url, local_ip, local_port_int, name)
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

def main():
    parser = argparse.ArgumentParser(description='OSC Relay Client')
    parser.add_argument('--nogui', action='store_true', help='Run without GUI (CLI mode)')
    parser.add_argument('--server', default=DEFAULT_SERVER_URL, help='WebSocket server URL')
    parser.add_argument('--local-ip', default=None, help='Local OSC server IP to forward messages to')
    parser.add_argument('--local-port', type=int, default=None, help='Local OSC server port to forward messages to')
    parser.add_argument('--name', default=socket.gethostname(), help='Receiver name')
    parser.add_argument('--debug', action='store_true', help='Enable debug logging')
    args = parser.parse_args()

    if args.debug:
        logger.setLevel(logging.DEBUG)

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
        if (args.local_ip is None and args.local_port is not None) or \
           (args.local_ip is not None and args.local_port is None):
            logger.error("Both --local-ip and --local-port must be specified for forwarding")
            sys.exit(1)
        client = OSCRelayClient(
            args.server, 
            args.local_ip, 
            args.local_port, 
            args.name
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