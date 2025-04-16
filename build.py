#!/usr/bin/env python3
"""
Build script for OSC Relay Client
This script builds the OSC Relay Client application for the current platform.
"""

import os
import sys
import platform
import subprocess
import shutil
import zipfile
import tempfile

def check_dependencies():
    """Check if required dependencies are installed."""
    try:
        import PyInstaller
        import PySide6
        import socketio
        import engineio
        import pythonosc
        import requests
        return True
    except ImportError as e:
        print(f"Missing dependency: {e}")
        print("Installing dependencies...")
        subprocess.run([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"], check=True)
        return True

def build_macos():
    """Build the application for macOS."""
    print("Building for macOS...")
    subprocess.run(["pyinstaller", "OSC_Relay_Client_mac.spec"], check=True)
    
    # Create zip file
    print("Creating zip file...")
    dist_dir = os.path.join(os.getcwd(), "dist")
    app_path = os.path.join(dist_dir, "OSC_Relay_Client.app")
    zip_path = os.path.join(dist_dir, "OSC_Relay_Client_macOS.zip")
    
    if os.path.exists(zip_path):
        os.remove(zip_path)
    
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for root, _, files in os.walk(app_path):
            for file in files:
                file_path = os.path.join(root, file)
                arcname = os.path.relpath(file_path, dist_dir)
                zipf.write(file_path, arcname)
    
    print(f"Build complete! The application is in {app_path}")
    print(f"A zip file has been created at {zip_path}")

def build_windows():
    """Build the application for Windows."""
    print("Building for Windows...")
    subprocess.run(["pyinstaller", "OSC_Relay_Client.spec"], check=True)
    
    # Create zip file
    print("Creating zip file...")
    dist_dir = os.path.join(os.getcwd(), "dist")
    exe_dir = os.path.join(dist_dir, "OSC_Relay_Client")
    zip_path = os.path.join(dist_dir, "OSC_Relay_Client_Windows.zip")
    
    if os.path.exists(zip_path):
        os.remove(zip_path)
    
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for root, _, files in os.walk(exe_dir):
            for file in files:
                file_path = os.path.join(root, file)
                arcname = os.path.relpath(file_path, dist_dir)
                zipf.write(file_path, arcname)
    
    print(f"Build complete! The application is in {exe_dir}")
    print(f"A zip file has been created at {zip_path}")

def main():
    """Main function."""
    print("Build script for OSC Relay Client")
    
    # Check if Python is installed
    if sys.version_info < (3, 10):
        print("Python 3.10 or later is required.")
        sys.exit(1)
    
    # Check dependencies
    check_dependencies()
    
    # Build for the current platform
    system = platform.system()
    if system == "Darwin":
        build_macos()
    elif system == "Windows":
        build_windows()
    else:
        print(f"Unsupported operating system: {system}")
        print("This script only supports macOS and Windows.")
        sys.exit(1)

if __name__ == "__main__":
    main() 