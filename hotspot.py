import json
import os
import subprocess
import threading
import time
import cv2
import numpy as np
from flask import Flask, jsonify, request, render_template_string, Response

# ---- Hotspot Management ----

HOTSPOT_SSID = "Dogmobile"
HOTSPOT_PASSWORD = "RowGlowBrev"
HOTSPOT_CON_NAME = "DogmobileHotspot"
HOTSPOT_GATEWAY_IP = "10.42.0.1"

STREAM_JPEG_QUALITY = 65
STREAM_THREAD_SHUTDOWN_TIMEOUT = 3

# ---- Network Configuration ----

NETWORKS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "networks.json")
WIFI_INTERFACE = "wlan1"
AP_INTERFACE = "wlan0"
# Brief pause (seconds) between stopping one network mode and starting another.
# Allows the OS to fully tear down the previous interface before reconnecting.
NETWORK_TRANSITION_DELAY = 1


def start_hotspot():
    """Turn the Pi into a Wi-Fi hotspot using NetworkManager."""
    try:
        # Delete any existing connection with this name
        subprocess.run(
            ["sudo", "nmcli", "connection", "delete", HOTSPOT_CON_NAME],
            capture_output=True
        )
        # Create a new hotspot
        subprocess.run([
            "sudo", "nmcli", "device", "wifi", "hotspot",
            "ifname", AP_INTERFACE,
            "con-name", HOTSPOT_CON_NAME,
            "ssid", HOTSPOT_SSID,
            "password", HOTSPOT_PASSWORD
        ], check=True, capture_output=True, text=True)
        print(f"✅ Hotspot '{HOTSPOT_SSID}' started")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ Failed to start hotspot: {e.stderr}")
        return False


def stop_hotspot():
    """Disable the hotspot and restore normal Wi-Fi."""
    try:
        subprocess.run(
            ["sudo", "nmcli", "connection", "down", HOTSPOT_CON_NAME],
            check=True, capture_output=True, text=True
        )
        subprocess.run(
            ["sudo", "nmcli", "connection", "delete", HOTSPOT_CON_NAME],
            capture_output=True
        )
        print("✅ Hotspot stopped")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ Failed to stop hotspot: {e.stderr}")
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


# ---- Saved Network Management ----

def load_saved_networks():
    """Load saved networks from networks.json. Returns a list of network dicts."""
    try:
        with open(NETWORKS_FILE, 'r') as f:
            data = json.load(f)
            return data.get('saved_networks', [])
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def save_network(name, ssid, password, icon="📶"):
    """Add or update a network entry in networks.json. Returns True on success."""
    networks = load_saved_networks()
    for net in networks:
        if net.get('ssid') == ssid:
            net.update({'name': name, 'password': password, 'icon': icon})
            break
    else:
        networks.append({'name': name, 'icon': icon, 'ssid': ssid, 'password': password})
    try:
        with open(NETWORKS_FILE, 'w') as f:
            json.dump({'saved_networks': networks}, f, indent=2)
        return True
    except Exception as e:
        print(f"❌ Failed to save network: {e}")
        return False


def scan_wifi():
    """Scan for available Wi-Fi networks via nmcli. Returns list sorted by signal strength."""
    try:
        result = subprocess.run(
            ["nmcli", "--terse", "--fields", "SSID,SIGNAL,SECURITY",
             "device", "wifi", "list", "ifname", WIFI_INTERFACE],
            capture_output=True, text=True, timeout=15
        )
        networks = []
        seen = set()
        for line in result.stdout.splitlines():
            parts = line.split(':')
            if len(parts) < 2:
                continue
            ssid = parts[0].strip()
            if not ssid or ssid in seen:
                continue
            try:
                signal = int(parts[1].strip())
            except ValueError:
                signal = 0
            security = parts[2].strip() if len(parts) > 2 else ""
            networks.append({'ssid': ssid, 'signal': signal, 'security': security})
            seen.add(ssid)
        networks.sort(key=lambda x: x['signal'], reverse=True)
        return networks
    except subprocess.TimeoutExpired:
        print("❌ Wi-Fi scan timed out")
        return []
    except Exception as e:
        print(f"❌ Failed to scan Wi-Fi: {e}")
        return []


def get_available_known_networks():
    """Cross-reference live scan results with saved networks. Returns matches sorted by signal."""
    saved = {net['ssid']: net for net in load_saved_networks()}
    if not saved:
        return []
    available = scan_wifi()
    matches = []
    for net in available:
        if net['ssid'] in saved:
            merged = dict(saved[net['ssid']])
            merged['signal'] = net['signal']
            matches.append(merged)
    return matches  # Already sorted by signal from scan_wifi()


def join_network(ssid, password):
    """Connect WIFI_INTERFACE to an existing Wi-Fi network via nmcli. Returns True on success."""
    try:
        cmd = ["sudo", "nmcli", "device", "wifi", "connect", ssid,
               "ifname", WIFI_INTERFACE]
        if password:
            cmd += ["password", password]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode == 0:
            print(f"✅ Connected to '{ssid}'")
            return True
        print(f"❌ Failed to connect to '{ssid}': {result.stderr.strip()}")
        return False
    except subprocess.TimeoutExpired:
        print(f"❌ Connection to '{ssid}' timed out")
        return False
    except Exception as e:
        print(f"❌ Error connecting to '{ssid}': {e}")
        return False


def disconnect_network():
    """Disconnect WIFI_INTERFACE from any joined Wi-Fi network. Returns True on success."""
    try:
        subprocess.run(
            ["sudo", "nmcli", "device", "disconnect", WIFI_INTERFACE],
            capture_output=True, text=True, timeout=10
        )
        print(f"✅ Disconnected {WIFI_INTERFACE}")
        return True
    except Exception as e:
        print(f"❌ Failed to disconnect: {e}")
        return False


def get_current_ip():
    """Get the current IPv4 address of WIFI_INTERFACE, or None if unavailable."""
    try:
        result = subprocess.run(
            ["ip", "-4", "addr", "show", WIFI_INTERFACE],
            capture_output=True, text=True, timeout=5
        )
        for line in result.stdout.splitlines():
            line = line.strip()
            if line.startswith("inet "):
                return line.split()[1].split('/')[0]
        return None
    except Exception:
        return None


# ---- Captive Portal HTML ----

SETUP_HTML = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, user-scalable=no">
    <title>Add Network — Dogmobile</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            background: #1a1a1a; color: white; font-family: Arial, sans-serif;
            display: flex; flex-direction: column; align-items: center;
            padding: 20px; min-height: 100vh;
        }
        h1 { margin-bottom: 20px; font-size: 22px; }
        h2 { margin: 15px 0 8px; font-size: 16px; color: #0078D7; }
        .section { width: 100%; max-width: 400px; margin-bottom: 20px; }
        .network-item {
            padding: 12px 16px; margin: 6px 0; border-radius: 8px;
            background: #333; cursor: pointer; display: flex;
            justify-content: space-between; align-items: center;
        }
        .network-item:active { background: #005fa3; }
        .network-item.selected { background: #0078D7; }
        .signal { color: #ccc; font-size: 13px; }
        input {
            width: 100%; padding: 12px; font-size: 16px; border-radius: 8px;
            border: none; background: #333; color: white; margin-top: 8px;
        }
        button {
            width: 100%; padding: 16px; font-size: 16px; font-weight: bold;
            border: none; border-radius: 8px; cursor: pointer;
            background: #0078D7; color: white; margin-top: 12px;
        }
        button:active { background: #005fa3; }
        #status { text-align: center; margin-top: 16px; color: #aaa; font-size: 14px; line-height: 1.6; }
        .loading { color: #888; text-align: center; padding: 20px; }
        a { color: #0078D7; }
    </style>
</head>
<body>
    <h1>➕ Add Network</h1>

    <div class="section">
        <h2>Nearby Networks</h2>
        <div id="networks-list"><div class="loading">🔍 Scanning…</div></div>
    </div>

    <div class="section" id="connect-form" style="display:none">
        <h2>Connect to: <span id="selected-ssid-label"></span></h2>
        <input type="text" id="ssid-input" placeholder="Network name (SSID)" />
        <input type="password" id="password-input" placeholder="Password (leave blank if open)" />
        <input type="text" id="name-input" placeholder="Friendly name (e.g. Home, Starbucks)" />
        <button onclick="connectNetwork()">Connect &amp; Save</button>
    </div>

    <div id="status"></div>

    <script>
        let selectedSSID = '';

        async function scanNetworks() {
            document.getElementById('networks-list').innerHTML = '<div class="loading">🔍 Scanning…</div>';
            try {
                const res = await fetch('/api/scan_networks');
                const data = await res.json();
                const list = document.getElementById('networks-list');
                if (!data.networks || data.networks.length === 0) {
                    list.innerHTML = '<div class="loading">No networks found. <a href="#" onclick="scanNetworks()">Retry</a></div>';
                    return;
                }
                list.innerHTML = data.networks.map(n =>
                    `<div class="network-item" onclick="selectNetwork(this, ${JSON.stringify(n.ssid)})">
                        <span>${n.ssid}</span>
                        <span class="signal">📶 ${n.signal}%</span>
                    </div>`
                ).join('');
            } catch(e) {
                document.getElementById('networks-list').innerHTML =
                    '<div class="loading">Scan failed. <a href="#" onclick="scanNetworks()">Retry</a></div>';
            }
        }

        function selectNetwork(el, ssid) {
            document.querySelectorAll('.network-item').forEach(e => e.classList.remove('selected'));
            el.classList.add('selected');
            selectedSSID = ssid;
            document.getElementById('ssid-input').value = ssid;
            document.getElementById('name-input').value = ssid;
            document.getElementById('password-input').value = '';
            document.getElementById('selected-ssid-label').textContent = ssid;
            document.getElementById('connect-form').style.display = 'block';
        }

        async function connectNetwork() {
            const ssid = document.getElementById('ssid-input').value.trim();
            const password = document.getElementById('password-input').value;
            const name = document.getElementById('name-input').value.trim() || ssid;
            if (!ssid) {
                document.getElementById('status').textContent = 'Please enter a network name.';
                return;
            }
            document.getElementById('status').textContent = '⏳ Saving and connecting…';
            try {
                const res = await fetch('/setup/connect', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({ssid, password, name})
                });
                const data = await res.json();
                if (data.success) {
                    document.getElementById('status').innerHTML =
                        '✅ Credentials saved! The Pi is connecting to <strong>' + ssid + '</strong>.<br>' +
                        'Please rejoin that network on your phone, then open<br>' +
                        '<strong>http://dogmobile.local:8080</strong>';
                } else {
                    document.getElementById('status').textContent = '❌ ' + (data.error || 'Connection failed');
                }
            } catch(e) {
                document.getElementById('status').textContent = '❌ Error: ' + e.message;
            }
        }

        scanNetworks();
    </script>
</body>
</html>
"""


# ---- PWA HTML ----

WEB_UI_HTML = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, user-scalable=no">
    <meta name="apple-mobile-web-app-capable" content="yes">
    <meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
    <meta name="apple-mobile-web-app-title" content="Dogmobile">
    <title>Dogmobile Remote</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            background: #1a1a1a; color: white; font-family: Arial, sans-serif;
            display: flex; flex-direction: column; align-items: center;
            padding: 20px; min-height: 100vh;
        }
        h1 { margin-bottom: 20px; font-size: 24px; }
        h2 { margin: 15px 0 10px; font-size: 18px; color: #0078D7; }
        .section { width: 100%; max-width: 400px; margin-bottom: 20px; }
        .video-section {
            width: 100%; max-width: 400px; margin-bottom: 20px;
        }
        .video-section img {
            width: 100%;
            border-radius: 8px;
            display: block;
            background: #000;
            min-height: 150px;
        }
        .btn-grid {
            display: grid; gap: 10px;
        }
        .cam-grid { grid-template-columns: repeat(2, 1fr); }
        .fan-grid { grid-template-columns: repeat(4, 1fr); }
        .fan-label {
            grid-column: 1 / -1; text-align: center;
            font-weight: bold; padding: 5px; background: #333; border-radius: 5px;
        }
        button {
            padding: 18px 10px; font-size: 16px; font-weight: bold;
            border: none; border-radius: 8px; cursor: pointer;
            background: #444; color: white;
            transition: background 0.15s;
            -webkit-tap-highlight-color: transparent;
        }
        button:active { background: #0078D7; }
        button.active { background: #00A0FF; }
        .status { color: #888; font-size: 14px; text-align: center; margin-top: 10px; }
    </style>
</head>
<body>
    <h1>🐕 Dogmobile</h1>

    <div class="video-section">
        <img src="/video_feed" alt="Camera Feed" onerror="this.style.opacity='0.3'">
    </div>

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
</html>
"""


# ---- MJPEG Streaming ----

def _open_camera(path):
    """Open a camera at the given path and configure it."""
    cap = cv2.VideoCapture(path, cv2.CAP_V4L2)
    if cap.isOpened():
        cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*'MJPG'))
        cap.set(cv2.CAP_PROP_FPS, 30)
    return cap


def _make_side_by_side(frames, target_h=240, target_w=320):
    """Compose a list of frames side by side into a single image."""
    resized = []
    for f in frames:
        h, w = f.shape[:2]
        if h == 0 or w == 0:
            resized.append(np.zeros((target_h, target_w, 3), dtype=np.uint8))
            continue
        scale = target_h / h
        new_w = int(w * scale)
        f_r = cv2.resize(f, (new_w, target_h))
        if new_w > target_w:
            x_off = (new_w - target_w) // 2
            f_r = f_r[:, x_off:x_off + target_w]
        elif new_w < target_w:
            canvas = np.zeros((target_h, target_w, 3), dtype=np.uint8)
            x_off = (target_w - new_w) // 2
            canvas[:, x_off:x_off + new_w] = f_r
            f_r = canvas
        resized.append(f_r)
    return np.hstack(resized)


# ---- Flask App Factory ----

def create_web_app(remote_server):
    """Create and return a Flask app wired to the RemoteServer."""
    app = Flask(__name__)

    @app.route('/')
    def index():
        return render_template_string(WEB_UI_HTML)

    @app.route('/video_feed')
    def video_feed():
        return Response(
            _stream_generator(remote_server),
            mimetype='multipart/x-mixed-replace; boundary=frame'
        )

    @app.route('/api/camera_mode')
    def camera_mode():
        state = remote_server.get_display_state()
        return jsonify({'mode': state.get('mode'), 'cam_keys': state.get('cam_keys')})

    @app.route('/api/command', methods=['POST'])
    def command():
        data = request.get_json()
        cmd_type = data.get('type')
        key = data.get('key')

        if cmd_type == 'camera' and key in ['0', '1', '2', '3']:
            remote_server.send_camera(key)
            return jsonify({"status": f"Camera → {key}"})
        elif cmd_type == 'fan' and key in list('asdfghjkzxcv'):
            remote_server.send_fan(key)
            return jsonify({"status": f"Fan → {key}"})
        else:
            return jsonify({"status": "Unknown command"}), 400

    @app.route('/setup')
    def setup():
        return render_template_string(SETUP_HTML)

    @app.route('/api/scan_networks')
    def api_scan_networks():
        networks = scan_wifi()
        return jsonify({'networks': networks})

    @app.route('/setup/connect', methods=['POST'])
    def setup_connect():
        data = request.get_json() or {}
        ssid = data.get('ssid', '').strip()
        password = data.get('password', '')
        name = (data.get('name', '') or ssid).strip()
        icon = data.get('icon', '📶')

        if not ssid:
            return jsonify({'success': False, 'error': 'SSID is required'}), 400

        save_network(name, ssid, password, icon)

        # Transition to the new network in a background thread so the HTTP
        # response can be sent before the hotspot goes down.
        threading.Thread(
            target=lambda: remote_server.switch_to_joined(ssid, password, name),
            daemon=True
        ).start()

        return jsonify({'success': True, 'ssid': ssid, 'name': name})

    @app.route('/api/network_status')
    def network_status():
        ip = get_current_ip() if remote_server.mode == 'joined' else HOTSPOT_GATEWAY_IP
        return jsonify({
            'mode': remote_server.mode,
            'network_name': remote_server.active_network_name,
            'ip': ip,
        })

    return app


def _stream_generator(remote_server):
    """Yield MJPEG frames from the RemoteServer's shared frame buffer."""
    while remote_server.is_running:
        jpeg = remote_server.get_current_jpeg()
        if jpeg is not None:
            yield (
                b'--frame\r\n'
                b'Content-Type: image/jpeg\r\n\r\n' +
                jpeg +
                b'\r\n'
            )
        else:
            time.sleep(0.033)


# ---- Remote Server ----

class RemoteServer:
    """Manages Wi-Fi connectivity + Flask web server + MJPEG camera stream lifecycle.

    Supports two modes:
    - ``'hotspot'``: Pi creates the Dogmobile AP (original behaviour).
    - ``'joined'``: Pi connects to an existing Wi-Fi network.

    ``smart_connect()`` automatically picks the best mode based on saved networks.
    """

    def __init__(self, send_camera_fn, send_fan_fn, camera_paths=None,
                 stop_display_fn=None, resume_display_fn=None,
                 get_display_state_fn=None, port=8080):
        self.send_camera = send_camera_fn
        self.send_fan = send_fan_fn
        self.camera_paths = camera_paths or {}
        self.stop_display_fn = stop_display_fn
        self.resume_display_fn = resume_display_fn
        self._get_display_state = get_display_state_fn or (lambda: {'mode': None, 'cam_keys': None})
        self.port = port

        self._running = False
        self._mode = None               # 'hotspot' | 'joined' | None
        self._active_network_name = None  # e.g. 'Dogmobile' | 'Home' | None
        self._streaming_active = threading.Event()
        self._current_jpeg = None
        self._jpeg_lock = threading.Lock()
        self._stream_thread = None
        self._server_thread = None
        self._app = None

    # ---- Properties ----

    @property
    def is_running(self):
        return self._running

    @property
    def mode(self):
        """Current connection mode: ``'hotspot'``, ``'joined'``, or ``None``."""
        return self._mode

    @property
    def active_network_name(self):
        """Human-readable name of the active network, or ``None`` when inactive."""
        return self._active_network_name

    # ---- Display state ----

    def get_display_state(self):
        """Return current display state dict: {'mode': ..., 'cam_keys': ...}."""
        return self._get_display_state()

    def get_current_jpeg(self):
        """Return the latest JPEG bytes, or None if not available."""
        with self._jpeg_lock:
            return self._current_jpeg

    # ---- Internal helpers ----

    def _start_server_components(self):
        """Start the background camera worker and the Flask daemon thread."""
        self._streaming_active.set()
        self._stream_thread = threading.Thread(
            target=self._camera_worker, daemon=True, name="MJPEGCameraWorker"
        )
        self._stream_thread.start()

        self._app = create_web_app(self)
        self._server_thread = threading.Thread(
            target=lambda: self._app.run(
                host='0.0.0.0',
                port=self.port,
                use_reloader=False,
                threaded=True
            ),
            daemon=True,
            name="FlaskServer"
        )
        self._server_thread.start()

    def _camera_worker(self):
        """Background thread: reads camera frames, encodes to JPEG, stores in buffer."""
        caps = {}
        last_mode = None
        last_cam_keys = None

        try:
            while self._streaming_active.is_set():
                state = self._get_display_state()
                mode = state.get('mode')
                cam_keys = tuple(state.get('cam_keys') or [])

                # Detect mode/camera change
                if mode != last_mode or cam_keys != last_cam_keys:
                    for cap in caps.values():
                        try:
                            cap.release()
                        except Exception:
                            pass
                    caps.clear()
                    last_mode = mode
                    last_cam_keys = cam_keys

                    if mode in ('1', '2', '3'):
                        path = self.camera_paths.get(mode)
                        if path:
                            cap = _open_camera(path)
                            if cap.isOpened():
                                caps[mode] = cap
                    elif mode == 'multi' and cam_keys:
                        for k in cam_keys:
                            path = self.camera_paths.get(k)
                            if path:
                                cap = _open_camera(path)
                                if cap.isOpened():
                                    caps[k] = cap

                jpeg = self._capture_jpeg(caps, mode, cam_keys)
                if jpeg is not None:
                    with self._jpeg_lock:
                        self._current_jpeg = jpeg
                else:
                    time.sleep(0.033)

        finally:
            for cap in caps.values():
                try:
                    cap.release()
                except Exception:
                    pass
            with self._jpeg_lock:
                self._current_jpeg = None

    def _capture_jpeg(self, caps, mode, cam_keys):
        """Read a frame (or composite) and return JPEG bytes, or None on failure."""
        if not caps:
            # No cameras available — show placeholder
            frame = np.zeros((240, 320, 3), dtype=np.uint8)
            cv2.putText(frame, "No camera", (60, 120),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (200, 200, 200), 2)
        elif mode in ('1', '2', '3'):
            cap = caps.get(mode)
            if not cap:
                return None
            ret, frame = cap.read()
            if not ret:
                return None
        elif mode == 'multi' and cam_keys:
            frames = []
            for k in cam_keys:
                cap = caps.get(k)
                if cap:
                    ret, f = cap.read()
                    frames.append(f if ret else np.zeros((240, 320, 3), dtype=np.uint8))
                else:
                    frames.append(np.zeros((240, 320, 3), dtype=np.uint8))
            if not frames:
                return None
            frame = _make_side_by_side(frames)
        else:
            return None

        ret, buf = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, STREAM_JPEG_QUALITY])
        return buf.tobytes() if ret else None

    # ---- Public API ----

    def start_hotspot_mode(self):
        """Start the Dogmobile hotspot, camera stream, and Flask web server."""
        if self._running:
            return True
        if not start_hotspot():
            return False
        self._start_server_components()
        self._mode = 'hotspot'
        self._active_network_name = 'Dogmobile'
        self._running = True
        print(f"🔥 Dogmobile hotspot active — http://{HOTSPOT_GATEWAY_IP}:{self.port}")
        return True

    def start_joined_mode(self, ssid, password, name=None):
        """Join an existing Wi-Fi network, then start the camera stream and Flask server."""
        if self._running:
            return True
        if not join_network(ssid, password):
            return False
        self._start_server_components()
        self._mode = 'joined'
        self._active_network_name = name or ssid
        self._running = True
        ip = get_current_ip()
        print(f"🌐 Connected to '{self._active_network_name}' — "
              f"http://{ip or 'dogmobile.local'}:{self.port}")
        return True

    def smart_connect(self, on_status=None):
        """Scan for saved networks and connect to the strongest one, or fall back to hotspot.

        ``on_status`` is an optional ``callable(str)`` for UI status messages.
        Returns ``(success: bool, mode: str|None, network_name: str|None)``.
        """
        if self._running:
            return True, self._mode, self._active_network_name

        if on_status:
            on_status("🔍 Scanning…")

        available = get_available_known_networks()
        if available:
            best = available[0]
            display_name = best.get('name') or best['ssid']
            if on_status:
                on_status(f"📶 Connecting to {display_name}…")
            if self.start_joined_mode(best['ssid'], best.get('password', ''), best.get('name')):
                return True, 'joined', self._active_network_name

        # Fall back to hotspot
        if on_status:
            on_status("📡 Starting hotspot…")
        if self.start_hotspot_mode():
            return True, 'hotspot', 'Dogmobile'

        return False, None, None

    def switch_to_joined(self, ssid, password, name=None):
        """Transition from hotspot mode to a joined network (captive portal callback).

        Stops the hotspot but keeps the Flask server running (bound to 0.0.0.0),
        then connects to the new network so clients can reach it via mDNS.
        """
        # Drop the hotspot interface; Flask keeps listening on 0.0.0.0
        stop_hotspot()
        time.sleep(NETWORK_TRANSITION_DELAY)  # Allow OS to tear down interface

        if join_network(ssid, password):
            self._mode = 'joined'
            self._active_network_name = name or ssid
            ip = get_current_ip()
            print(f"🌐 Switched to '{self._active_network_name}' — "
                  f"http://{ip or 'dogmobile.local'}:{self.port}")
            return True

        # Joining failed — restart the hotspot so the Pi is still reachable
        print("❌ Failed to join network — restarting hotspot")
        start_hotspot()
        self._mode = 'hotspot'
        self._active_network_name = 'Dogmobile'
        return False

    def start(self):
        """Start the Dogmobile hotspot (backward-compatible alias for start_hotspot_mode)."""
        return self.start_hotspot_mode()

    def stop(self):
        """Stop the MJPEG stream and disconnect from the current network mode."""
        if not self._running:
            return

        self._streaming_active.clear()
        if self._stream_thread and self._stream_thread.is_alive():
            self._stream_thread.join(timeout=STREAM_THREAD_SHUTDOWN_TIMEOUT)

        if self._mode == 'hotspot':
            stop_hotspot()
        elif self._mode == 'joined':
            disconnect_network()

        self._mode = None
        self._active_network_name = None
        self._running = False
        print("🛑 Remote server stopped")
