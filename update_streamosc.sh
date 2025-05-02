#!/bin/bash

# Configuration
APP_NAME="streamosc"
APP_DIR="/var/www/myapp/massdevserver"
GIT_BRANCH="master"
USER="www-data"

# Exit on any error
set -e

echo "🔒 Marking repository as safe for Git system-wide..."
sudo git config --system --add safe.directory "$APP_DIR"

echo "📁 Entering app directory..."
cd "$APP_DIR"

echo "📦 Committing local changes..."
sudo -u $USER git add .
sudo -u $USER git commit -m "Auto-update from server" || echo "✅ No changes to commit"

echo "🔄 Pulling latest from GitHub..."
if ! sudo -u $USER git pull --rebase; then
  echo "⚠️  Pull failed — forcing local version to GitHub..."
  sudo -u $USER git push origin $GIT_BRANCH --force
else
  echo "🚀 Pushing merged changes to GitHub..."
  sudo -u $USER git push origin $GIT_BRANCH
fi

echo "🔁 Restarting streamosc service..."
sudo systemctl restart $APP_NAME

echo "✅ Update complete."
