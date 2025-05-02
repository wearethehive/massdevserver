# OSC Relay Client

This client allows you to receive OSC messages from the Stream OSC relay service in external applications.

## Features

- Connect to the Stream OSC WebSocket relay service
- Receive OSC messages in real-time
- Optionally forward messages to a local OSC server
- Automatic reconnection if the connection is lost
- Detailed logging and statistics

## Requirements

- Python 3.6+
- Required Python packages:
  - python-socketio
  - python-osc

## Installation

1. Install the required packages:

```bash
pip install python-socketio python-osc
```

2. Make the script executable (Unix/Linux/macOS):

```bash
chmod +x osc_relay_client.py
```

## Usage

### Basic Usage

To simply receive and log OSC messages:

```bash
python osc_relay_client.py --server http://your-server:7401 --name "My Client"
```

### Forwarding to a Local OSC Server

To receive messages and forward them to a local OSC server:

```bash
python osc_relay_client.py --server http://your-server:7401 --name "My Client" --local-ip 127.0.0.1 --local-port 57120
```

### Full Options

```
usage: osc_relay_client.py [-h] [--server SERVER] [--local-ip LOCAL_IP]
                           [--local-port LOCAL_PORT] [--name NAME] [--debug]

OSC Relay Client

optional arguments:
  -h, --help            show this help message and exit
  --server SERVER       WebSocket server URL
  --local-ip LOCAL_IP   Local OSC server IP to forward messages to
  --local-port LOCAL_PORT
                        Local OSC server port to forward messages to
  --name NAME           Receiver name
  --debug               Enable debug logging
```

## Examples

### Receiving Messages Only

```bash
python osc_relay_client.py --server http://192.168.1.100:7401 --name "MaxMSP Client"
```

### Forwarding to Max/MSP

```bash
python osc_relay_client.py --server http://192.168.1.100:7401 --name "MaxMSP Bridge" --local-ip 127.0.0.1 --local-port 57120
```

### Forwarding to Processing

```bash
python osc_relay_client.py --server http://192.168.1.100:7401 --name "Processing Bridge" --local-ip 127.0.0.1 --local-port 12000
```

## Integrating with Other Applications

### Max/MSP

1. Create a UDP receive object in Max/MSP
2. Set the port to match the `--local-port` parameter
3. Run the OSC relay client with forwarding enabled

### Processing

1. Use the OSCP5 library in Processing
2. Create a receiver on the port specified by `--local-port`
3. Run the OSC relay client with forwarding enabled

### Pure Data

1. Create a UDP receive object in Pure Data
2. Set the port to match the `--local-port` parameter
3. Run the OSC relay client with forwarding enabled

## Troubleshooting

- If messages aren't being received, check that the server URL is correct
- If forwarding isn't working, ensure the local OSC server is running and listening on the specified port
- Enable debug logging with `--debug` for more detailed information
- Check the log file for error messages

## Advanced Usage

### Custom Message Processing

You can modify the `on_relay_message` method in the `OSCRelayClient` class to process messages in custom ways instead of just forwarding them.

### Running as a Service

On Linux/macOS, you can create a systemd service to run the client automatically:

```ini
[Unit]
Description=OSC Relay Client
After=network.target

[Service]
ExecStart=/usr/bin/python3 /path/to/osc_relay_client.py --server http://your-server:7401 --name "Service Client" --local-ip 127.0.0.1 --local-port 57120
Restart=always
User=yourusername

[Install]
WantedBy=multi-user.target
```

Save this to `/etc/systemd/system/osc-relay.service` and then:

```bash
sudo systemctl enable osc-relay
sudo systemctl start osc-relay
``` 