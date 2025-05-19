import cv2
import numpy as np
import threading
from pynput import keyboard
import time
from board import SCL, SDA
import busio
from adafruit_pca9685 import PCA9685

# Add UI control globals
UI_STATE = {
    'camera_menu_open': False,
    'fan_menu_open': False,
    'multiview_select': False,
    'selected_camera': None,
    'last_touch': None
}

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

# Target height for video display
TARGET_HEIGHT = int(SCREEN_HEIGHT * 2/3)
UI_HEIGHT = SCREEN_HEIGHT - TARGET_HEIGHT

# Define UI regions for touch detection
def define_ui_regions():
    # Main buttons
    camera_btn = {'x1': 100, 'y1': TARGET_HEIGHT + 20, 'x2': 300, 'y2': SCREEN_HEIGHT - 20}
    fan_btn = {'x1': SCREEN_WIDTH - 300, 'y1': TARGET_HEIGHT + 20, 'x2': SCREEN_WIDTH - 100, 'y2': SCREEN_HEIGHT - 20}
    
    # Camera menu buttons
    cam_menu_y = TARGET_HEIGHT + 20
    cam_menu_height = UI_HEIGHT - 40
    btn_width = 150
    cam1_btn = {'x1': 50, 'y1': cam_menu_y, 'x2': 50 + btn_width, 'y2': cam_menu_y + cam_menu_height}
    cam2_btn = {'x1': 220, 'y1': cam_menu_y, 'x2': 220 + btn_width, 'y2': cam_menu_y + cam_menu_height}
    cam3_btn = {'x1': 390, 'y1': cam_menu_y, 'x2': 390 + btn_width, 'y2': cam_menu_y + cam_menu_height}
    multi_btn = {'x1': 560, 'y1': cam_menu_y, 'x2': 560 + btn_width, 'y2': cam_menu_y + cam_menu_height}
    
    # Fan speed buttons
    fan_menu_y = TARGET_HEIGHT + 20
    fan_menu_height = UI_HEIGHT - 40
    fan_btn_width = 100
    fan0_btn = {'x1': 600, 'y1': fan_menu_y, 'x2': 600 + fan_btn_width, 'y2': fan_menu_y + fan_menu_height}
    fan20_btn = {'x1': 710, 'y1': fan_menu_y, 'x2': 710 + fan_btn_width, 'y2': fan_menu_y + fan_menu_height}
    fan40_btn = {'x1': 820, 'y1': fan_menu_y, 'x2': 820 + fan_btn_width, 'y2': fan_menu_y + fan_menu_height}
    fan60_btn = {'x1': 600, 'y1': fan_menu_y, 'x2': 600 + fan_btn_width, 'y2': fan_menu_y + fan_menu_height}
    fan80_btn = {'x1': 710, 'y1': fan_menu_y, 'x2': 710 + fan_btn_width, 'y2': fan_menu_y + fan_menu_height}
    fan100_btn = {'x1': 820, 'y1': fan_menu_y, 'x2': 820 + fan_btn_width, 'y2': fan_menu_y + fan_menu_height}
    
    return {
        'camera_btn': camera_btn,
        'fan_btn': fan_btn,
        'cam1_btn': cam1_btn, 
        'cam2_btn': cam2_btn,
        'cam3_btn': cam3_btn,
        'multi_btn': multi_btn,
        'fan0_btn': fan0_btn,
        'fan20_btn': fan20_btn,
        'fan40_btn': fan40_btn,
        'fan60_btn': fan60_btn,
        'fan80_btn': fan80_btn,
        'fan100_btn': fan100_btn
    }

UI_REGIONS = define_ui_regions()

def draw_button(frame, region, text, icon=None, active=False):
    """Draw a button on the frame"""
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
    
    # Draw icon if provided
    if icon is not None:
        # Here you would draw the icon (simplifying for now)
        icon_size = 24
        icon_x = x1 + 10
        icon_y = y1 + (y2 - y1 - icon_size) // 2
        
        # For camera icon (simple representation)
        if icon == "camera":
            cv2.rectangle(frame, (icon_x, icon_y), (icon_x + icon_size, icon_y + icon_size), (255, 255, 255), 1)
            cv2.circle(frame, (icon_x + icon_size//2, icon_y + icon_size//2), icon_size//3, (255, 255, 255), 1)
        # For fan icon (simple representation)
        elif icon == "fan":
            cv2.circle(frame, (icon_x + icon_size//2, icon_y + icon_size//2), icon_size//2, (255, 255, 255), 1)
            cv2.line(frame, (icon_x + icon_size//2, icon_y + icon_size//4), (icon_x + icon_size//2, icon_y + 3*icon_size//4), (255, 255, 255), 2)
            cv2.line(frame, (icon_x + icon_size//4, icon_y + icon_size//2), (icon_x + 3*icon_size//4, icon_y + icon_size//2), (255, 255, 255), 2)

def draw_ui(frame):
    """Draw the UI elements on the frame"""
    # Draw separator line
    cv2.line(frame, (0, TARGET_HEIGHT), (SCREEN_WIDTH, TARGET_HEIGHT), (80, 80, 80), 2)
    
    # Draw main buttons
    draw_button(frame, UI_REGIONS['camera_btn'], "Cameras", "camera", UI_STATE['camera_menu_open'])
    draw_button(frame, UI_REGIONS['fan_btn'], "Fan", "fan", UI_STATE['fan_menu_open'])
    
    # Draw camera menu if open
    if UI_STATE['camera_menu_open']:
        # Draw submenu background
        cv2.rectangle(frame, (40, TARGET_HEIGHT + 10), (730, SCREEN_HEIGHT - 10), (20, 20, 20), -1)
        cv2.rectangle(frame, (40, TARGET_HEIGHT + 10), (730, SCREEN_HEIGHT - 10), (60, 60, 60), 2)
        
        # Draw camera buttons
        draw_button(frame, UI_REGIONS['cam1_btn'], "Camera 1")
        draw_button(frame, UI_REGIONS['cam2_btn'], "Camera 2")
        draw_button(frame, UI_REGIONS['cam3_btn'], "Camera 3")
        draw_button(frame, UI_REGIONS['multi_btn'], "Multi View")
    
    # Draw fan menu if open
    if UI_STATE['fan_menu_open']:
        # Draw submenu background
        cv2.rectangle(frame, (SCREEN_WIDTH - 730, TARGET_HEIGHT + 10), (SCREEN_WIDTH - 40, SCREEN_HEIGHT - 10), (20, 20, 20), -1)
        cv2.rectangle(frame, (SCREEN_WIDTH - 730, TARGET_HEIGHT + 10), (SCREEN_WIDTH - 40, SCREEN_HEIGHT - 10), (60, 60, 60), 2)
        
        # Draw fan speed buttons
        draw_button(frame, UI_REGIONS['fan0_btn'], "0%")
        draw_button(frame, UI_REGIONS['fan20_btn'], "20%")
        draw_button(frame, UI_REGIONS['fan40_btn'], "40%")
        draw_button(frame, UI_REGIONS['fan60_btn'], "60%")
        draw_button(frame, UI_REGIONS['fan80_btn'], "80%")
        draw_button(frame, UI_REGIONS['fan100_btn'], "100%")
    
    # Draw multiview selection prompt if active
    if UI_STATE['multiview_select']:
        # Draw overlay message
        cv2.rectangle(frame, (SCREEN_WIDTH//4, SCREEN_HEIGHT//3), (3*SCREEN_WIDTH//4, 2*SCREEN_HEIGHT//3), (40, 40, 40), -1)
        cv2.rectangle(frame, (SCREEN_WIDTH//4, SCREEN_HEIGHT//3), (3*SCREEN_WIDTH//4, 2*SCREEN_HEIGHT//3), (0, 120, 255), 2)
        
        text = "Select two cameras for multiview"
        font = cv2.FONT_HERSHEY_SIMPLEX
        text_size = cv2.getTextSize(text, font, 1.0, 2)[0]
        text_x = SCREEN_WIDTH//2 - text_size[0]//2
        text_y = SCREEN_HEIGHT//2 - 40
        cv2.putText(frame, text, (text_x, text_y), font, 1.0, (255, 255, 255), 2)
        
        # Draw camera selection buttons
        button_width = 100
        button_height = 60
        spacing = 30
        
        for i in range(1, 4):
            x = SCREEN_WIDTH//2 - 3*button_width//2 - spacing + (i-1)*(button_width+spacing)
            y = SCREEN_HEIGHT//2
            
            # Check if already selected
            is_selected = str(i) in multiview_selection
            color = (0, 200, 0) if is_selected else (0, 70, 150)
            
            cv2.rectangle(frame, (x, y), (x+button_width, y+button_height), color, -1)
            cv2.rectangle(frame, (x, y), (x+button_width, y+button_height), (255, 255, 255), 2)
            
            text = f"Cam {i}"
            text_size = cv2.getTextSize(text, font, 0.7, 2)[0]
            text_x = x + (button_width - text_size[0]) // 2
            text_y = y + (button_height + text_size[1]) // 2
            cv2.putText(frame, text, (text_x, text_y), font, 0.7, (255, 255, 255), 2)

def handle_touch(event, x, y, flags, param):
    """Handle mouse/touch events"""
    global UI_STATE, multiview_selection, current_mode
    
    if event == cv2.EVENT_LBUTTONDOWN:
        print(f"Touch at ({x}, {y})")
        UI_STATE['last_touch'] = (x, y)
        
        # Check if touch is in camera button
        if y > TARGET_HEIGHT:  # Only process UI touches below the video area
            if is_point_in_region(x, y, UI_REGIONS['camera_btn']):
                UI_STATE['camera_menu_open'] = not UI_STATE['camera_menu_open']
                UI_STATE['fan_menu_open'] = False
                print(f"Camera menu {'opened' if UI_STATE['camera_menu_open'] else 'closed'}")
                return
                
            elif is_point_in_region(x, y, UI_REGIONS['fan_btn']):
                UI_STATE['fan_menu_open'] = not UI_STATE['fan_menu_open']
                UI_STATE['camera_menu_open'] = False
                print(f"Fan menu {'opened' if UI_STATE['fan_menu_open'] else 'closed'}")
                return
        
        # Handle camera menu selections
        if UI_STATE['camera_menu_open']:
            if is_point_in_region(x, y, UI_REGIONS['cam1_btn']):
                switch_mode('1')
                UI_STATE['camera_menu_open'] = False
                return
                
            elif is_point_in_region(x, y, UI_REGIONS['cam2_btn']):
                switch_mode('2')
                UI_STATE['camera_menu_open'] = False
                return
                
            elif is_point_in_region(x, y, UI_REGIONS['cam3_btn']):
                switch_mode('3')
                UI_STATE['camera_menu_open'] = False
                return
                
            elif is_point_in_region(x, y, UI_REGIONS['multi_btn']):
                print("📺 Select two cameras for multiview")
                multiview_selection = []
                UI_STATE['multiview_select'] = True
                UI_STATE['camera_menu_open'] = False
                return
        
        # Handle fan menu selections
        if UI_STATE['fan_menu_open']:
            duty = None
            if is_point_in_region(x, y, UI_REGIONS['fan0_btn']):
                duty = 0x0000
                percent = 0
            elif is_point_in_region(x, y, UI_REGIONS['fan20_btn']): 
                duty = 0x3333
                percent = 20
            elif is_point_in_region(x, y, UI_REGIONS['fan40_btn']):
                duty = 0x6666
                percent = 40
            elif is_point_in_region(x, y, UI_REGIONS['fan60_btn']):
                duty = 0x9999
                percent = 60
            elif is_point_in_region(x, y, UI_REGIONS['fan80_btn']):
                duty = 0xCCCC
                percent = 80
            elif is_point_in_region(x, y, UI_REGIONS['fan100_btn']):
                duty = 0xFFFF
                percent = 100
                
            if duty is not None:
                fan.duty_cycle = duty
                print(f"Fan speed set to {percent}%")
                UI_STATE['fan_menu_open'] = False
                return
        
        # Handle multiview camera selection
        if UI_STATE['multiview_select']:
            # Simple button layout for camera selection
            button_width = 100
            button_height = 60
            spacing = 30
            
            for i in range(1, 4):
                x_btn = SCREEN_WIDTH//2 - 3*button_width//2 - spacing + (i-1)*(button_width+spacing)
                y_btn = SCREEN_HEIGHT//2
                
                if x > x_btn and x < x_btn+button_width and y > y_btn and y < y_btn+button_height:
                    camera = str(i)
                    
                    # Toggle selection
                    if camera in multiview_selection:
                        multiview_selection.remove(camera)
                    else:
                        if len(multiview_selection) < 2:
                            multiview_selection.append(camera)
                    
                    print(f"Selected cameras: {multiview_selection}")
                    
                    # If we have 2 selections, activate multiview
                    if len(multiview_selection) == 2:
                        switch_mode('multi', multiview_selection)
                        UI_STATE['multiview_select'] = False
                    
                    return

def is_point_in_region(x, y, region):
    """Check if a point is inside a region"""
    return (x >= region['x1'] and x <= region['x2'] and 
            y >= region['y1'] and y <= region['y2'])

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
        
        # Set up mouse callback for touch events
        cv2.setMouseCallback(window_name, handle_touch)
        
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
                # Now use TARGET_HEIGHT constant (2/3 of screen)
                
                # Resize to half screen width and target height maintaining aspect ratio
                h, w = frame.shape[:2]
                half_width = SCREEN_WIDTH // 2
                
                # Calculate scaling factors
                scale_w = half_width / w
                scale_h = TARGET_HEIGHT / h
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

            # Draw the UI elements
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
    
    # Set up mouse callback for touch events
    cv2.setMouseCallback(window_name, handle_touch)
    
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
            
            # Use TARGET_HEIGHT instead of calculating each time
            
            # Get original frame dimensions
            h, w = frame.shape[:2]
            
            # Calculate scaling factors
            scale_w = SCREEN_WIDTH / w
            scale_h = TARGET_HEIGHT / h
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
            
            # Draw the UI elements
            draw_ui(background)
            
            # Display the result
            cv2.imshow(window_name, background)
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break
                
        cap.release()

    return threading.Thread(target=display)

def switch_mode(mode, cam_keys=None):
    global current_mode, stop_thread, display_thread

    # Avoid joining thread when called from UI callback
    is_from_callback = threading.current_thread() == display_thread
    
    # Mark current thread for stopping
    stop_thread = True
    
    # Store the old thread to clean up later (if needed)
    old_thread = display_thread
    
    # Update current mode
    current_mode = mode
    
    # Create new thread based on selected mode
    if mode == 'multi':
        if not cam_keys or len(cam_keys) != 2:
            print("⚠️ Need exactly 2 cameras for multiview")
            cam_keys = ['1', '2']  # Default to cameras 1 and 2
        display_thread = show_multiview(cam_keys)
    elif mode in ['1', '2', '3']:
        display_thread = show_single(mode)
    else:
        return
        
    # Start the new display thread
    stop_thread = False
    display_thread.start()
    
    # Only try to join the old thread if:
    # 1. It exists
    # 2. It's not the current thread
    # 3. It's still alive
    if old_thread and not is_from_callback and old_thread.is_alive():
        try:
            old_thread.join(timeout=1.0)  # Use timeout to prevent blocking
        except RuntimeError:
            # If we still get an error, just let it go
            print("⚠️ Thread cleanup skipped")
            pass

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
    print("📱 Touch UI available for camera and fan control")

    # Auto-start in multiview mode with Cameras 1 and 2
    switch_mode('multi', ['1', '2'])

    with keyboard.Listener(on_press=on_press, on_release=on_release) as listener:
        listener.join()

if __name__ == "__main__":
    main()
