#!/bin/bash

# Build script for OSC Relay Client

# Check if Python is installed
if ! command -v python &> /dev/null; then
    echo "Python is not installed. Please install Python 3.10 or later."
    exit 1
fi

# Check if pip is installed
if ! command -v pip &> /dev/null; then
    echo "pip is not installed. Please install pip."
    exit 1
fi

# Install dependencies
echo "Installing dependencies..."
pip install -r requirements.txt

# Detect OS
if [[ "$OSTYPE" == "darwin"* ]]; then
    # macOS
    echo "Building for macOS..."
    pyinstaller OSC_Relay_Client_mac.spec
    
    # Create zip file
    echo "Creating zip file..."
    cd dist
    zip -r OSC_Relay_Client_macOS.zip OSC_Relay_Client.app/
    cd ..
    
    echo "Build complete! The application is in dist/OSC_Relay_Client.app"
    echo "A zip file has been created at dist/OSC_Relay_Client_macOS.zip"
    
elif [[ "$OSTYPE" == "msys" || "$OSTYPE" == "win32" ]]; then
    # Windows
    echo "Building for Windows..."
    pyinstaller OSC_Relay_Client.spec
    
    # Create zip file
    echo "Creating zip file..."
    cd dist
    powershell Compress-Archive -Path OSC_Relay_Client -DestinationPath OSC_Relay_Client_Windows.zip -Force
    cd ..
    
    echo "Build complete! The application is in dist/OSC_Relay_Client"
    echo "A zip file has been created at dist/OSC_Relay_Client_Windows.zip"
    
else
    # Linux or other
    echo "Unsupported operating system: $OSTYPE"
    echo "This script only supports macOS and Windows."
    exit 1
fi 