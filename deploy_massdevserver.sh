#!/bin/bash

# Configuration
APP_NAME="streamosc"
APP_USER="www-data"
APP_DIR="/var/www/myapp/massdevserver"
REPO_URL="https://github.com/youruser/yourrepo.git"  # Optional
PYTHON_VERSION="3.10"
SERVICE_FILE="/etc/systemd/system/${APP_NAME}.service"

# Exit on error
set -e

echo "🔧 Installing dependencies..."
sudo apt update
sudo apt install -y python${PYTHON_VERSION} python${PYTHON_VERSION}-venv python${PYTHON_VERSION}-dev git curl

echo "📁 Creating app directory..."
sudo mkdir -p "$APP_DIR"
sudo chown -R $APP_USER:$APP_USER "$APP_DIR"

# Optional: clone repo (uncomment if needed)
# echo "📥 Cloning repository..."
# sudo git clone "$REPO_URL" "$APP_DIR"

echo "🐍 Setting up virtual environment..."
cd "$APP_DIR"
sudo -u $APP_USER python${PYTHON_VERSION} -m venv venv
sudo -u $APP_USER ./venv/bin/pip install --upgrade pip
sudo -u $APP_USER ./venv/bin/pip install gunicorn eventlet flask flask_socketio python-osc flask-limiter python-dotenv flask-caching

echo "🧪 Writing .env file..."
cat <<EOF | sudo tee "$APP_DIR/.env"
API_KEYS=your-production-api-key
HOST=0.0.0.0
PORT=80
DEBUG=False
LOG_LEVEL=INFO
ALLOWED_ORIGINS=http://localhost
SECRET_KEY=supersecretkey123
EOF
sudo chown $APP_USER:$APP_USER "$APP_DIR/.env"

echo "📝 Creating systemd service..."
cat <<EOF | sudo tee "$SERVICE_FILE"
[Unit]
Description=StreamOSC Flask App (Gunicorn + Eventlet)
After=network.target

[Service]
User=${APP_USER}
WorkingDirectory=${APP_DIR}
Environment="PATH=${APP_DIR}/venv/bin"
ExecStart=${APP_DIR}/venv/bin/gunicorn --worker-class eventlet -w 4 -b 0.0.0.0:80 streamosc:app
Restart=always
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

echo "🔄 Reloading systemd and starting service..."
sudo systemctl daemon-reload
sudo systemctl enable $APP_NAME
sudo systemctl restart $APP_NAME

echo "✅ Deployment complete. Check status with:"
echo "    sudo systemctl status $APP_NAME"
