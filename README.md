# OSC Relay Server

A secure WebSocket-based OSC relay server for production use.

## Security Features

- API key authentication for all endpoints
- Rate limiting to prevent abuse
- CORS protection with configurable allowed origins
- SSL/TLS support for secure communication
- Comprehensive logging
- Environment-based configuration

## Prerequisites

- Python 3.8 or higher
- SSL certificates for HTTPS
- A production web server (e.g., Nginx)

## Installation

1. Clone the repository:
   ```bash
   git clone <repository-url>
   cd osc-relay-server
   ```

2. Create a virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

4. Configure environment variables:
   - Copy `.env.example` to `.env`
   - Update the values in `.env` with your production settings
   - Generate a secure `SECRET_KEY`
   - Add your API keys
   - Configure SSL certificate paths
   - Set allowed origins

## Production Deployment

1. Set up SSL certificates:
   - Obtain SSL certificates from a trusted provider
   - Place them in a secure location
   - Update `SSL_CERT_PATH` and `SSL_KEY_PATH` in `.env`

2. Configure Nginx as a reverse proxy:
   ```nginx
   server {
       listen 443 ssl;
       server_name your-domain.com;

       ssl_certificate /path/to/certificate.pem;
       ssl_certificate_key /path/to/private.key;

       location / {
           proxy_pass http://localhost:7401;
           proxy_http_version 1.1;
           proxy_set_header Upgrade $http_upgrade;
           proxy_set_header Connection "upgrade";
           proxy_set_header Host $host;
           proxy_set_header X-Real-IP $remote_addr;
       }
   }
   ```

3. Start the server using Gunicorn:
   ```bash
   gunicorn --worker-class eventlet -w 1 -b 0.0.0.0:7401 streamosc:app
   ```

4. Set up a process manager (e.g., systemd):
   ```ini
   [Unit]
   Description=OSC Relay Server
   After=network.target

   [Service]
   User=osc-relay
   WorkingDirectory=/path/to/osc-relay-server
   Environment="PATH=/path/to/osc-relay-server/venv/bin"
   ExecStart=/path/to/osc-relay-server/venv/bin/gunicorn --worker-class eventlet -w 1 -b 0.0.0.0:7401 streamosc:app
   Restart=always

   [Install]
   WantedBy=multi-user.target
   ```

## Monitoring

- Logs are written to the file specified in `LOG_FILE`
- Set `LOG_LEVEL` to control verbosity
- Monitor the logs for security events and errors

## Security Best Practices

1. Keep all dependencies updated
2. Regularly rotate API keys
3. Monitor logs for suspicious activity
4. Use strong SSL certificates
5. Implement proper firewall rules
6. Regular security audits

## Client Integration

Clients must:
1. Include an API key in all requests
2. Connect using WSS (secure WebSocket)
3. Handle rate limiting responses
4. Implement proper error handling

Example client connection:
```javascript
const socket = io('wss://your-domain.com', {
    query: {
        api_key: 'your-api-key'
    }
});
```

## License

[Your License] 