# Mass Development Server

A web-based OSC message server for development and testing.

## Deployment Instructions

### Prerequisites
- Python 3.8 or higher
- Nginx web server
- Systemd (for service management)

### Installation Steps

1. Clone the repository:
```bash
git clone <repository-url>
cd massdevserver
```

2. Create and activate a virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Create a `.env` file:
```bash
cp .env.example .env
# Edit .env with your configuration
```

5. Configure Nginx:
Create a new file `/etc/nginx/sites-available/massdevserver`:
```nginx
server {
    listen 80;
    server_name your-domain.com;

    location / {
        proxy_pass http://127.0.0.1:7401;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

6. Enable the Nginx site:
```bash
sudo ln -s /etc/nginx/sites-available/massdevserver /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl restart nginx
```

7. Set up the systemd service:
```bash
# Edit the service file with your paths
sudo cp massdevserver.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable massdevserver
sudo systemctl start massdevserver
```

8. Set up SSL with Let's Encrypt:
```bash
sudo apt install certbot python3-certbot-nginx
sudo certbot --nginx -d your-domain.com
```

### Security Considerations

1. Always use HTTPS in production
2. Keep your API keys secure
3. Regularly update dependencies
4. Monitor server logs for issues
5. Set up proper firewall rules

### Maintenance

- Check logs: `sudo journalctl -u massdevserver`
- Restart service: `sudo systemctl restart massdevserver`
- Update code: Pull latest changes and restart service

## Development

For local development:
```bash
python streamosc.py
```

## License

[Your License Here] 