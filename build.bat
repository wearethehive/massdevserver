@echo off
echo Build script for OSC Relay Client

REM Check if Python is installed
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo Python is not installed. Please install Python 3.10 or later.
    exit /b 1
)

REM Check if pip is installed
pip --version >nul 2>&1
if %errorlevel% neq 0 (
    echo pip is not installed. Please install pip.
    exit /b 1
)

REM Install dependencies
echo Installing dependencies...
pip install -r requirements.txt

REM Build for Windows
echo Building for Windows...
pyinstaller OSC_Relay_Client.spec

REM Create zip file
echo Creating zip file...
cd dist
powershell Compress-Archive -Path OSC_Relay_Client -DestinationPath OSC_Relay_Client_Windows.zip -Force
cd ..

echo Build complete! The application is in dist\OSC_Relay_Client
echo A zip file has been created at dist\OSC_Relay_Client_Windows.zip 