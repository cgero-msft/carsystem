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

# Hardcode a reasonable default resolution that works on Pi displays
SCREEN_WIDTH = 1024
SCREEN_HEIGHT = 600

# Skip the detection logic since it's returning incorrect values
def get_screen_resolution():
    print(f"📺 Using fixed resolution: {SCREEN_WIDTH}x{SCREEN_HEIGHT}")
    return SCREEN_WIDTH, SCREEN_HEIGHT

# Use a global variable to store screen dimensions
SCREEN_WIDTH, SCREEN_HEIGHT = get_screen_resolution()

##### UI SECTION #####
UI_STATE = {
    'camera_menu_open': False,
    'multiview_select': False,
    'last_touch': None
}

UI_REGIONS = {
    'camera_btn': {'x1': 10, 'y1': SCREEN_HEIGHT - 90, 'x2': 110, 'y2': SCREEN_HEIGHT - 10},
    'cam1_btn': {'x1': 10, 'y1': SCREEN_HEIGHT - 190, 'x2': 110, 'y2': SCREEN_HEIGHT - 110},
    'cam2_btn': {'x1': 120, 'y1': SCREEN_HEIGHT - 190, 'x2': 220, 'y2': SCREEN_HEIGHT - 110},
    'cam3_btn': {'x1': 230, 'y1': SCREEN_HEIGHT - 190, 'x2': 330, 'y2': SCREEN_HEIGHT - 110},
    'multi_btn': {'x1': 340, 'y1': SCREEN_HEIGHT - 190, 'x2': 440, 'y2': SCREEN_HEIGHT - 110}
}

def draw_button(frame, region, text, icon=None, active=False):
    """Draw a button on the frame."""
    x1, y1 = region['x1'], region['y1']
    x2, y2 = region['x2'], region['y2']

    # Draw button background
    color = (0, 120, 255) if active else (0, 70, 150)
    cv2.rectangle(frame, (x1, y1), (x2, y2), color, -1)
    cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 100, 200), 2)

    # Draw text
    font = cv2.FONT_HERSHEY_SIMPLEX
    text_size = cv2.getTextSize(text, font, 0.8, 2)[0]
    text_x = x1 + (x2 - x1 - text_size[0]) // 2
    text_y = y1 + (y2 - y1 + text_size[1]) // 2
    cv2.putText(frame, text, (text_x, text_y), font, 0.8, (255, 255, 255), 2)


def draw_multiview_selection_prompt(frame):
    """Draw the multiview selection prompt."""
    text = "Select two cameras for multiview"
    font = cv2.FONT_HERSHEY_SIMPLEX
    text_size = cv2.getTextSize(text, font, 1.0, 2)[0]
    text_x = SCREEN_WIDTH // 2 - text_size[0] // 2
    text_y = SCREEN_HEIGHT // 2 - 40
    cv2.putText(frame, text, (text_x, text_y), font, 1.0, (255, 255, 255), 2)


def is_point_in_region(x, y, region):
    """Check if a point is inside a region."""
    return region['x1'] <= x <= region['x2'] and region['y1'] <= y <= region['y2']


def draw_ui(frame):
    """Draw the UI elements on the frame."""
    # Draw separator line
    cv2.line(frame, (0, SCREEN_HEIGHT - 100), (SCREEN_WIDTH, SCREEN_HEIGHT - 100), (80, 80, 80), 2)

    # Draw camera button
    if not UI_STATE['camera_menu_open']:
        draw_button(frame, UI_REGIONS['camera_btn'], "Camera", "camera", active=False)
    else:
        # Draw expanded camera menu
        draw_button(frame, UI_REGIONS['cam1_btn'], "Cam1", active=False)
        draw_button(frame, UI_REGIONS['cam2_btn'], "Cam2", active=False)
        draw_button(frame, UI_REGIONS['cam3_btn'], "Cam3", active=False)
        draw_button(frame, UI_REGIONS['multi_btn'], "Multi", active=UI_STATE['multiview_select'])

    # Highlight multiview selection if active
    if UI_STATE['multiview_select']:
        draw_multiview_selection_prompt(frame)


def simulate_keystroke(key):
    """Simulate a keystroke."""
    print(f"Simulating keystroke: {key}")
    on_press(keyboard.KeyCode.from_char(key))


def handle_touch(event, x, y, flags, param):
    """Handle mouse/touch events."""
    global UI_STATE, multiview_selection, current_mode

    if event == cv2.EVENT_LBUTTONDOWN:
        print(f"Touch at ({x}, {y})")
        UI_STATE['last_touch'] = (x, y)

        # Check if touch is in the camera button
        if is_point_in_region(x, y, UI_REGIONS['camera_btn']):
            UI_STATE['camera_menu_open'] = not UI_STATE['camera_menu_open']
            print(f"Camera menu {'opened' if UI_STATE['camera_menu_open'] else 'closed'}")
            return

        # Handle camera menu selections
        if UI_STATE['camera_menu_open']:
            if is_point_in_region(x, y, UI_REGIONS['cam1_btn']):
                simulate_keystroke('1')
                UI_STATE['camera_menu_open'] = False
                return
            elif is_point_in_region(x, y, UI_REGIONS['cam2_btn']):
                simulate_keystroke('2')
                UI_STATE['camera_menu_open'] = False
                return
            elif is_point_in_region(x, y, UI_REGIONS['cam3_btn']):
                simulate_keystroke('3')
                UI_STATE['camera_menu_open'] = False
                return
            elif is_point_in_region(x, y, UI_REGIONS['multi_btn']):
                print("📺 Select two cameras for multiview")
                multiview_selection = []
                UI_STATE['multiview_select'] = True
                return

        # Handle multiview camera selection
        if UI_STATE['multiview_select']:
            for cam, region in [('1', UI_REGIONS['cam1_btn']), ('2', UI_REGIONS['cam2_btn']), ('3', UI_REGIONS['cam3_btn'])]:
                if is_point_in_region(x, y, region):
                    if cam not in multiview_selection:
                        multiview_selection.append(cam)
                        print(f"✅ Selected Camera {cam}")
                    if len(multiview_selection) == 2:
                        simulate_keystroke('0')  # Simulate multiview keystroke
                        for cam in multiview_selection:
                            simulate_keystroke(cam)
                        UI_STATE['multiview_select'] = False
                    return


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
    global stop_thread, SCREEN_WIDTH, SCREEN_HEIGHT
    stop_thread = False
    print(f"📷 Showing multiview: Camera {cam_keys[0]} and Camera {cam_keys[1]}")

    # Ensure we have valid screen dimensions
    if SCREEN_WIDTH <= 0 or SCREEN_HEIGHT <= 0:
        print("⚠️ Invalid screen dimensions, resetting to defaults")
        SCREEN_WIDTH, SCREEN_HEIGHT = 1024, 600

    def display():
        caps = []
        for k in cam_keys:
            cap = cv2.VideoCapture(camera_paths[k], cv2.CAP_V4L2)
            cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*'MJPG'))
            cap.set(cv2.CAP_PROP_FPS, 30)
            caps.append(cap)

        # Create window with Raspberry Pi optimized settings
        window_name = 'Camera View'
        cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)
        
        # Allow window system to initialize
        time.sleep(0.5)
        
        # Force window to be positioned at 0,0 and set size explicitly
        cv2.moveWindow(window_name, 0, 0)
        cv2.resizeWindow(window_name, SCREEN_WIDTH, SCREEN_HEIGHT)
        
        # Set fullscreen 
        cv2.setWindowProperty(window_name, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)
        
        # Show initial black background while loading
        black_bg = np.zeros((SCREEN_HEIGHT, SCREEN_WIDTH, 3), dtype=np.uint8)
        cv2.imshow(window_name, black_bg)
        cv2.waitKey(1)

        while not stop_thread:
            # Create a fresh black background for each frame
            background = np.zeros((SCREEN_HEIGHT, SCREEN_WIDTH, 3), dtype=np.uint8)
            
            frames = []
            for cap, k in zip(caps, cam_keys):
                ret, frame = cap.read()
                if not ret:
                    print(f"⚠️ Camera {k} failed to read")
                    frame = np.zeros((480, 640, 3), dtype=np.uint8)
                
                # Calculate target height - use the same calculation method for all modes
                target_height = SCREEN_HEIGHT // 3 * 2  # Use 2/3 of screen height consistently
                
                # Resize to half screen width and target height maintaining aspect ratio
                h, w = frame.shape[:2]
                half_width = SCREEN_WIDTH // 2
                
                # Calculate scaling factors
                scale_w = half_width / w
                scale_h = target_height / h
                scale = min(scale_w, scale_h)  # Maintain aspect ratio
                
                # Calculate new dimensions
                new_w = int(w * scale)
                new_h = int(h * scale)
                
                # Resize the frame
                frame = cv2.resize(frame, (new_w, new_h))
                
                frames.append(frame)

            # Put frames side by side with horizontal centering
            combined_width = frames[0].shape[1] + frames[1].shape[1]
            x_offset = (SCREEN_WIDTH - combined_width) // 2
            
            # Position frames at the top with consistent height
            y_offset = 0
            
            # Place frames on background
            for i, frame in enumerate(frames):
                x_pos = x_offset + (i * frames[0].shape[1])
                background[y_offset:y_offset+frame.shape[0], x_pos:x_pos+frame.shape[1]] = frame

            draw_ui(background)
            cv2.imshow(window_name, background)
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break

        for cap in caps:
            cap.release()

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

    # Use the same window name as multiview for persistence
    window_name = 'Camera View'
    cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)
    cv2.setWindowProperty(window_name, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)
    
    # Show initial black background while loading
    black_bg = np.zeros((SCREEN_HEIGHT, SCREEN_WIDTH, 3), dtype=np.uint8)
    cv2.imshow(window_name, black_bg)
    cv2.waitKey(1)

    def display():
        while not stop_thread:
            ret, frame = cap.read()
            if not ret:
                time.sleep(0.1)
                continue
            
            # Calculate target height - use the same calculation method for all modes
            target_height = SCREEN_HEIGHT // 3 * 2  # Use 2/3 of screen height consistently
            
            # Get original frame dimensions
            h, w = frame.shape[:2]
            
            # Calculate scaling factors
            scale_w = SCREEN_WIDTH / w
            scale_h = target_height / h
            scale = min(scale_w, scale_h)  # Maintain aspect ratio
            
            # Calculate new dimensions
            new_w = int(w * scale)
            new_h = int(h * scale)
            
            # Resize the frame
            frame = cv2.resize(frame, (new_w, new_h))
            
            # Create a black background image with screen dimensions
            background = np.zeros((SCREEN_HEIGHT, SCREEN_WIDTH, 3), dtype=np.uint8)
            
            # Calculate horizontal centering
            x_offset = (SCREEN_WIDTH - new_w) // 2
            
            # Position at the top of the screen
            y_offset = 0
            
            # Place the frame on the black background
            background[y_offset:y_offset+new_h, x_offset:x_offset+new_w] = frame
            
            draw_ui(background)
            cv2.imshow(window_name, background)
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break
                
        cap.release()

    return threading.Thread(target=display)

def switch_mode(mode, cam_keys=None):
    global current_mode, stop_thread, display_thread

    # Mark old thread for stopping but don't destroy window
    stop_thread = True
    if display_thread and display_thread.is_alive():
        # Show a black frame before switching
        black_bg = np.zeros((SCREEN_HEIGHT, SCREEN_WIDTH, 3), dtype=np.uint8)
        cv2.namedWindow('Camera View', cv2.WINDOW_NORMAL)
        cv2.setWindowProperty('Camera View', cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)
        cv2.imshow('Camera View', black_bg)
        cv2.waitKey(1)
        
        # Now wait for thread to finish
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

