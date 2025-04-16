# OSC Relay Client

A client application for relaying OSC messages between devices.

## Building the Application

### Using GitHub Actions (Recommended)

This repository includes GitHub Actions workflows that automatically build the application for both macOS and Windows. To use this:

1. Push your code to a GitHub repository
2. Go to the "Actions" tab in your repository
3. Select the "Build OSC Relay Client" workflow
4. Click "Run workflow" to manually trigger a build
5. Once the build completes, you can download the built application from the artifacts section

### Building Locally

#### macOS

1. Install Python 3.10 or later
2. Install the required dependencies:
   ```
   pip install -r requirements.txt
   ```
3. Build the application:
   ```
   pyinstaller OSC_Relay_Client_mac.spec
   ```
4. The built application will be in the `dist` folder as `OSC_Relay_Client.app`

#### Windows

1. Install Python 3.10 or later
2. Install the required dependencies:
   ```
   pip install -r requirements.txt
   ```
3. Build the application:
   ```
   pyinstaller OSC_Relay_Client.spec
   ```
4. The built application will be in the `dist` folder as `OSC_Relay_Client.exe`

## Usage

1. Launch the application
2. Enter the server URL
3. Enter your client name
4. (Optional) Configure local OSC device settings
5. Click "Start" to begin receiving OSC messages

## License

[Your License Here] 