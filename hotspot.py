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
            "ifname", "wlan0",
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
    """Manages the hotspot + Flask web server + MJPEG camera stream lifecycle."""

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
        self._streaming_active = threading.Event()
        self._current_jpeg = None
        self._jpeg_lock = threading.Lock()
        self._stream_thread = None
        self._server_thread = None
        self._app = None

    @property
    def is_running(self):
        return self._running

    def get_display_state(self):
        """Return current display state dict: {'mode': ..., 'cam_keys': ...}."""
        return self._get_display_state()

    def get_current_jpeg(self):
        """Return the latest JPEG bytes, or None if not available."""
        with self._jpeg_lock:
            return self._current_jpeg

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

    def start(self):
        """Start the hotspot, camera stream worker, and Flask web server."""
        if self._running:
            return True

        if not start_hotspot():
            return False

        # Start background camera reader
        self._streaming_active.set()
        self._stream_thread = threading.Thread(
            target=self._camera_worker, daemon=True, name="MJPEGCameraWorker"
        )
        self._stream_thread.start()

        # Start Flask server
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

        self._running = True
        print(f"🌐 Web UI available at http://{HOTSPOT_GATEWAY_IP}:{self.port}")
        return True

    def stop(self):
        """Stop the MJPEG stream and hotspot (Flask daemon thread dies naturally)."""
        if not self._running:
            return

        self._streaming_active.clear()
        # Wait briefly for camera worker to release cameras
        if self._stream_thread and self._stream_thread.is_alive():
            self._stream_thread.join(timeout=STREAM_THREAD_SHUTDOWN_TIMEOUT)

        stop_hotspot()
        self._running = False
        print("🛑 Remote server stopped")
