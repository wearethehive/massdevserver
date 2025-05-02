from flask import send_file

@app.route('/download/<platform>')
def download_client(platform):
    if platform == 'mac':
        return send_file('clients/mac_client.zip', as_attachment=True)
    elif platform == 'windows':
        return send_file('clients/windows_client.zip', as_attachment=True)
    else:
        return 'Invalid platform', 400 