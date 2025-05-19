import cv2
import numpy as np
import threading
from pynput import keyboard
import time
from board import SCL, SDA
import busio
from adafruit_pca9685 import PCA9685

##### CAMERA SECTION #####
camera_paths = {
    '1': '/dev/v4l/by-path/platform-fd500000.pcie-pci-0000:01:00.0-usb-0:1.1.4:1.0-video-index0',
    '2': '/dev/v4l/by-path/platform-fd500000.pcie-pci-0000:01:00.0-usb-0:1.1.3:1.0-video-index0',
    '3': '/dev/v4l/by-path/platform-fd500000.pcie-pci-0000:01:00.0-usb-0:1.1.2:1.0-video-index0'
}

current_mode = None
stop_thread = False
display_thread = None
multiview_selection = []

# Get system screen resolution - Pi-specific approach
def get_screen_resolution():
    try:
        # Try to use Pi-specific method if available
        import subprocess
        output = subprocess.check_output("tvservice -s", shell=True).decode()
        resolution = output.split(",")[1].split(" ")[2]
        width, height = map(int, resolution.split("x"))
        print(f"📺 Detected screen resolution: {width}x{height}")
        return width, height
    except:
        # Fallback method
        print("📺 Using fallback resolution detection")
        temp = np.zeros((1, 1, 3), dtype=np.uint8)
        cv2.namedWindow('temp', cv2.WINDOW_NORMAL)
        cv2.setWindowProperty('temp', cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)
        screen_width = cv2.getWindowImageRect('temp')[2]
        screen_height = cv2.getWindowImageRect('temp')[3]
        cv2.destroyWindow('temp')
        print(f"📺 Detected screen resolution: {screen_width}x{screen_height}")
        return screen_width, screen_height

# Use a global variable to store screen dimensions
SCREEN_WIDTH, SCREEN_HEIGHT = get_screen_resolution()

def get_single_frame(path):
    cap = cv2.VideoCapture(path)
    if not cap.isOpened():
        print(f"❌ Could not open {path}")
        return np.zeros((SCREEN_HEIGHT, SCREEN_WIDTH, 3), dtype=np.uint8)
    ret, frame = cap.read()
    cap.release()
    if not ret:
        return np.zeros((SCREEN_HEIGHT, SCREEN_WIDTH, 3), dtype=np.uint8)
    return cv2.resize(frame, (SCREEN_WIDTH, SCREEN_HEIGHT))

def show_multiview(cam_keys):
    global stop_thread
    stop_thread = False
    print(f"📷 Showing multiview: Camera {cam_keys[0]} and Camera {cam_keys[1]}")

    def display():
        caps = []
        for k in cam_keys:
            cap = cv2.VideoCapture(camera_paths[k], cv2.CAP_V4L2)
            cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*'MJPG'))
            cap.set(cv2.CAP_PROP_FPS, 30)
            caps.append(cap)

        # Create window with Raspberry Pi optimized settings
        window_name = 'MultiView (press q to exit)'
        cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)
        # Force window to be positioned at 0,0 and set size explicitly
        cv2.moveWindow(window_name, 0, 0)
        cv2.resizeWindow(window_name, SCREEN_WIDTH, SCREEN_HEIGHT)
        # Set fullscreen after positioning
        cv2.setWindowProperty(window_name, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)

        while not stop_thread:
            frames = []
            for cap, k in zip(caps, cam_keys):
                ret, frame = cap.read()
                if not ret:
                    print(f"⚠️ Camera {k} failed to read")
                    frame = np.zeros((480, 640, 3), dtype=np.uint8)
                
                # Resize to half screen width but maintain aspect ratio
                h, w = frame.shape[:2]
                half_width = SCREEN_WIDTH // 2
                aspect = w / h
                new_height = int(half_width / aspect)
                frame = cv2.resize(frame, (half_width, new_height))
                
                # If height is not equal to screen height, pad with black
                if new_height < SCREEN_HEIGHT:
                    pad_top = (SCREEN_HEIGHT - new_height) // 2
                    pad_bottom = SCREEN_HEIGHT - new_height - pad_top
                    frame = cv2.copyMakeBorder(frame, pad_top, pad_bottom, 0, 0, 
                                             cv2.BORDER_CONSTANT, value=[0, 0, 0])
                frames.append(frame)

            combined = np.hstack(frames)
            cv2.imshow('MultiView (press q to exit)', combined)
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break

        for cap in caps:
            cap.release()
        cv2.destroyAllWindows()

    return threading.Thread(target=display)

def show_single(cam_key):
    global stop_thread
    stop_thread = False
    print(f"🔎 Fullscreen view: Camera {cam_key}")
    path = camera_paths[cam_key]
    cap = cv2.VideoCapture(path)
    if not cap.isOpened():
        print(f"❌ Failed to open {path}")
        return None

    # Create window with Raspberry Pi optimized settings
    window_name = f'Camera {cam_key} (press q to exit)'
    cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)
    # Force window to be positioned at 0,0 and set size explicitly
    cv2.moveWindow(window_name, 0, 0)
    cv2.resizeWindow(window_name, SCREEN_WIDTH, SCREEN_HEIGHT)
    # Set fullscreen after positioning
    cv2.setWindowProperty(window_name, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)

    def display():
        while not stop_thread:
            ret, frame = cap.read()
            if not ret:
                continue
                
            # Keep aspect ratio when resizing to full screen
            h, w = frame.shape[:2]
            aspect = w / h
            
            if SCREEN_WIDTH / SCREEN_HEIGHT > aspect:
                # Screen is wider than video
                new_h = SCREEN_HEIGHT
                new_w = int(new_h * aspect)
                frame = cv2.resize(frame, (new_w, new_h))
                
                # Center horizontally
                if new_w < SCREEN_WIDTH:
                    pad_left = (SCREEN_WIDTH - new_w) // 2
                    pad_right = SCREEN_WIDTH - new_w - pad_left
                    frame = cv2.copyMakeBorder(frame, 0, 0, pad_left, pad_right, 
                                             cv2.BORDER_CONSTANT, value=[0, 0, 0])
            else:
                # Screen is taller than video
                new_w = SCREEN_WIDTH
                new_h = int(new_w / aspect)
                frame = cv2.resize(frame, (new_w, new_h))
                
                # Center vertically
                if new_h < SCREEN_HEIGHT:
                    pad_top = (SCREEN_HEIGHT - new_h) // 2
                    pad_bottom = SCREEN_HEIGHT - new_h - pad_top
                    frame = cv2.copyMakeBorder(frame, pad_top, pad_bottom, 0, 0, 
                                             cv2.BORDER_CONSTANT, value=[0, 0, 0])
                    
            cv2.imshow(window_name, frame)
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break
                
        cap.release()
        cv2.destroyAllWindows()

    return threading.Thread(target=display)

def switch_mode(mode, cam_keys=None):
    global current_mode, stop_thread, display_thread

    stop_thread = True
    if display_thread and display_thread.is_alive():
        display_thread.join()

    current_mode = mode

    if mode == 'multi':
        display_thread = show_multiview(cam_keys)
    elif mode in ['1', '2', '3']:
        display_thread = show_single(mode)
    else:
        return

    display_thread.start()

##### FAN SECTION #####
i2c = busio.I2C(SCL, SDA)
pca = PCA9685(i2c)
pca.frequency = 250
fan = pca.channels[0]

duty_lookup = {
    'a': 0x0000,    # 0%
    's': 0x3333,    # 20%
    'd': 0x6666,    # 40%
    'f': 0x9999,    # 60%
    'g': 0xCCCC,    # 80%
    'h': 0xFFFF     # 100%
}

##### HOTKEYS #####
def on_press(key):
    global multiview_selection, current_mode

    try:
        if hasattr(key, 'char'):
            c = key.char.lower()

            # Fan control
            if c in duty_lookup:
                duty = duty_lookup[c]
                fan.duty_cycle = duty
                percent = int((duty / 0xFFFF) * 100)
                print(f"[KEY '{c.upper()}'] → Fan speed set to {percent}%")

            # Fullscreen camera mode
            elif c in ['1', '2', '3'] and current_mode != 'multi_select':
                switch_mode(c)

            # Enter multi-select mode
            elif c == '0':
                print("📺 Entering multi-select mode: Press 2 camera numbers (1-3)")
                multiview_selection = []
                current_mode = 'multi_select'

            # Select cameras for multiview
            elif current_mode == 'multi_select' and c in ['1', '2', '3']:
                if c not in multiview_selection:
                    multiview_selection.append(c)
                    print(f"✅ Selected Camera {c}")
                if len(multiview_selection) == 2:
                    switch_mode('multi', multiview_selection)
                    multiview_selection = []

    except Exception as e:
        print(f"❗ Keyboard error: {e}")

def on_release(key):
    if key == keyboard.Key.esc:
        print("👋 Exiting...")
        fan.duty_cycle = 0x0000
        pca.deinit()
        global stop_thread
        stop_thread = True
        if display_thread and display_thread.is_alive():
            display_thread.join()
        return False  # This stops the keyboard listener

##### MAIN ENTRY POINT #####
def main():
    print("🎥 Webcam viewer ready")
    print("🕹️  Hotkeys:\n  - 1/2/3 = Fullscreen view\n  - 0 + two cameras = Multiview\n  - A/S/D/F/G/H = Fan speed\n  - ESC = Quit")

    # Auto-start in multiview mode with Cameras 1 and 2
    switch_mode('multi', ['1', '2'])

    with keyboard.Listener(on_press=on_press, on_release=on_release) as listener:
        listener.join()

if __name__ == "__main__":
    main()
