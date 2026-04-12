import subprocess
import threading
from flask import Flask, jsonify, request, render_template_string

# ---- Hotspot Configuration ----

HOTSPOT_SSID = "Dogmobile"
HOTSPOT_PASSWORD = "RowGlowBrev"
HOTSPOT_CON_NAME = "DogmobileHotspot"
HOTSPOT_INTERFACE = "wlan0"
HOTSPOT_IP = "10.42.0.1"

# ---- Hotspot Management ----

def start_hotspot():
    """Turn the Pi into a Wi-Fi hotspot using NetworkManager."""
    try:
        # Delete any existing connection with this name (ignore errors)
        subprocess.run(
            ["sudo", "nmcli", "connection", "delete", HOTSPOT_CON_NAME],
            capture_output=True
        )
        # Create a new hotspot
        subprocess.run([
            "sudo", "nmcli", "device", "wifi", "hotspot",
            "ifname", HOTSPOT_INTERFACE,
            "con-name", HOTSPOT_CON_NAME,
            "ssid", HOTSPOT_SSID,
            "password", HOTSPOT_PASSWORD
        ], check=True, capture_output=True, text=True)
        print(f"Hotspot '{HOTSPOT_SSID}' started")
        return True
    except subprocess.CalledProcessError as e:
        print(f"Failed to start hotspot: {e.stderr}")
        return False


def stop_hotspot():
    """Disable the hotspot."""
    try:
        subprocess.run(
            ["sudo", "nmcli", "connection", "down", HOTSPOT_CON_NAME],
            check=True, capture_output=True, text=True
        )
        subprocess.run(
            ["sudo", "nmcli", "connection", "delete", HOTSPOT_CON_NAME],
            capture_output=True
        )
        print("Hotspot stopped")
        return True
    except subprocess.CalledProcessError as e:
        print(f"Failed to stop hotspot: {e.stderr}")
        return False


def is_hotspot_active():
    """Check if the hotspot connection is currently active."""
    try:
        result = subprocess.run(
            ["nmcli", "-t", "-f", "NAME,TYPE,DEVICE", "connection", "show", "--active"],
            capture_output=True, text=True
        )
        return HOTSPOT_CON_NAME in result.stdout
    except Exception:
        return False


# ---- PWA Web UI HTML ----

WEB_UI_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, user-scalable=no">
    <meta name="apple-mobile-web-app-capable" content="yes">
    <meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
    <meta name="apple-mobile-web-app-title" content="Dogmobile">
    <link rel="manifest" href="/manifest.json">
    <title>Dogmobile</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            background: #1a1a1a;
            color: white;
            font-family: Arial, sans-serif;
            display: flex;
            flex-direction: column;
            align-items: center;
            padding: 20px;
            min-height: 100vh;
        }
        h1 { margin-bottom: 20px; font-size: 24px; }
        h2 { margin: 15px 0 10px; font-size: 18px; color: #0078D7; }
        .section { width: 100%; max-width: 400px; margin-bottom: 20px; }
        .btn-grid { display: grid; gap: 10px; }
        .cam-grid { grid-template-columns: repeat(2, 1fr); }
        .fan-grid { grid-template-columns: repeat(4, 1fr); }
        button {
            padding: 18px 10px;
            font-size: 16px;
            font-weight: bold;
            border: none;
            border-radius: 8px;
            cursor: pointer;
            background: #444444;
            color: white;
            transition: background 0.15s;
            -webkit-tap-highlight-color: transparent;
        }
        button:active { background: #0078D7; }
        .status {
            color: #888;
            font-size: 14px;
            text-align: center;
            margin-top: 10px;
        }
    </style>
</head>
<body>
    <h1>🐶 Dogmobile</h1>

    <div class="section">
        <h2>📷 Camera</h2>
        <div class="btn-grid cam-grid">
            <button onclick="sendCmd('camera', '1')">Rowley</button>
            <button onclick="sendCmd('camera', '2')">Glow</button>
            <button onclick="sendCmd('camera', '3')">Brevity</button>
            <button onclick="sendCmd('camera', '0')">Multi</button>
        </div>
    </div>

    <div class="section">
        <h2>🌀 Fan — Rowley</h2>
        <div class="btn-grid fan-grid">
            <button onclick="sendCmd('fan', 'a')">Off</button>
            <button onclick="sendCmd('fan', 's')">Low</button>
            <button onclick="sendCmd('fan', 'd')">Med</button>
            <button onclick="sendCmd('fan', 'f')">High</button>
        </div>
    </div>

    <div class="section">
        <h2>🌀 Fan — Glow</h2>
        <div class="btn-grid fan-grid">
            <button onclick="sendCmd('fan', 'g')">Off</button>
            <button onclick="sendCmd('fan', 'h')">Low</button>
            <button onclick="sendCmd('fan', 'j')">Med</button>
            <button onclick="sendCmd('fan', 'k')">High</button>
        </div>
    </div>

    <div class="section">
        <h2>🌀 Fan — Brevity</h2>
        <div class="btn-grid fan-grid">
            <button onclick="sendCmd('fan', 'z')">Off</button>
            <button onclick="sendCmd('fan', 'x')">Low</button>
            <button onclick="sendCmd('fan', 'c')">Med</button>
            <button onclick="sendCmd('fan', 'v')">High</button>
        </div>
    </div>

    <div class="status" id="status">Ready</div>

    <script>
        async function sendCmd(type, key) {
            document.getElementById('status').textContent = 'Sending...';
            try {
                const res = await fetch('/api/command', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({type: type, key: key})
                });
                const data = await res.json();
                document.getElementById('status').textContent = data.status || 'OK';
            } catch(e) {
                document.getElementById('status').textContent = 'Error: ' + e.message;
            }
            setTimeout(() => {
                document.getElementById('status').textContent = 'Ready';
            }, 1500);
        }
    </script>
</body>
</html>"""

MANIFEST_JSON = """{
    "name": "Dogmobile",
    "short_name": "Dogmobile",
    "description": "Remote control for the Dogmobile car system",
    "start_url": "/",
    "display": "fullscreen",
    "background_color": "#1a1a1a",
    "theme_color": "#0078D7",
    "icons": []
}"""


# ---- Flask Web Server ----

def create_web_app(send_camera_fn, send_fan_fn):
    """Create and return a Flask app wired to the car system controls."""
    app = Flask(__name__)

    @app.route('/')
    def index():
        return render_template_string(WEB_UI_HTML)

    @app.route('/manifest.json')
    def manifest():
        return app.response_class(
            response=MANIFEST_JSON,
            status=200,
            mimetype='application/manifest+json'
        )

    @app.route('/api/command', methods=['POST'])
    def command():
        data = request.get_json()
        if not data:
            return jsonify({"status": "Invalid request"}), 400
        cmd_type = data.get('type')
        key = data.get('key')

        if cmd_type == 'camera' and key in ('0', '1', '2', '3'):
            send_camera_fn(key)
            return jsonify({"status": f"Camera \u2192 {key}"})
        elif cmd_type == 'fan' and key in list('asdfghjkzxcv'):
            send_fan_fn(key)
            return jsonify({"status": f"Fan \u2192 {key}"})
        else:
            return jsonify({"status": "Unknown command"}), 400

    return app


# ---- RemoteServer class ----

class RemoteServer:
    """Manages the hotspot + Flask web server lifecycle."""

    def __init__(self, send_camera_fn, send_fan_fn, port=8080):
        self.send_camera = send_camera_fn
        self.send_fan = send_fan_fn
        self.port = port
        self.server_thread = None
        self.app = None
        self._running = False

    @property
    def is_running(self):
        return self._running

    def start(self):
        """Start the hotspot and web server."""
        if self._running:
            return True

        if not start_hotspot():
            return False

        self.app = create_web_app(self.send_camera, self.send_fan)
        self.server_thread = threading.Thread(
            target=lambda: self.app.run(
                host='0.0.0.0',
                port=self.port,
                use_reloader=False,
                threaded=True
            ),
            daemon=True
        )
        self.server_thread.start()
        self._running = True
        print(f"Web UI available at http://{HOTSPOT_IP}:{self.port}")
        return True

    def stop(self):
        """Stop the hotspot. The Flask daemon thread will terminate when the process exits,
        or be replaced on the next call to start()."""
        if not self._running:
            return
        stop_hotspot()
        self._running = False
        self.app = None
        self.server_thread = None
        print("Remote server stopped")
