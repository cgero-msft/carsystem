import cv2
import numpy as np
import threading
from pynput import keyboard
import time
from board import SCL, SDA
import busio
from adafruit_pca9685 import PCA9685
import tkinter as tk
# Fix the import - use the UIOverlay class instead
from UI import UIOverlay

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

        # Calculate exact half width for each camera
        half_width = SCREEN_WIDTH // 2

        while not stop_thread:
            # Create a fresh black background for each frame
            background = np.zeros((SCREEN_HEIGHT, SCREEN_WIDTH, 3), dtype=np.uint8)
            
            for i, (cap, k) in enumerate(zip(caps, cam_keys)):
                ret, frame = cap.read()
                if not ret:
                    print(f"⚠️ Camera {k} failed to read")
                    frame = np.zeros((480, 640, 3), dtype=np.uint8)
                
                # Get original frame dimensions
                h, w = frame.shape[:2]
                
                # Calculate scaling factors to FILL exactly half screen width and full height
                scale_w = half_width / w
                scale_h = SCREEN_HEIGHT / h
                scale = max(scale_w, scale_h)  # Use max to fill entire area (will crop)
                
                # Calculate the dimensions after scaling
                scaled_w = int(w * scale)
                scaled_h = int(h * scale)
                
                # Resize frame to the larger size
                frame_resized = cv2.resize(frame, (scaled_w, scaled_h))
                
                # Calculate center crop to get exact dimensions
                # Find the center point
                center_x = scaled_w // 2
                center_y = scaled_h // 2
                
                # Calculate the crop boundaries for exact half width and full height
                crop_x_start = center_x - (half_width // 2)
                crop_y_start = center_y - (SCREEN_HEIGHT // 2)
                
                # Ensure crop boundaries are within the image
                crop_x_start = max(0, min(crop_x_start, scaled_w - half_width))
                crop_y_start = max(0, min(crop_y_start, scaled_h - SCREEN_HEIGHT))
                
                # Extract the correctly sized center portion
                crop_x_end = crop_x_start + half_width
                crop_y_end = crop_y_start + SCREEN_HEIGHT
                
                # Handle case where scaled image isn't big enough
                if crop_x_end > scaled_w:
                    crop_x_end = scaled_w
                if crop_y_end > scaled_h:
                    crop_y_end = scaled_h
                
                # Crop the frame to focus on center while filling view
                frame_cropped = frame_resized[crop_y_start:crop_y_end, crop_x_start:crop_x_end]
                
                # Handle case where cropped frame doesn't match required dimensions
                final_h, final_w = frame_cropped.shape[:2]
                if final_w != half_width or final_h != SCREEN_HEIGHT:
                    # Create a black canvas of exactly the right size
                    exact_size = np.zeros((SCREEN_HEIGHT, half_width, 3), dtype=np.uint8)
                    # Place the cropped frame centered in the canvas
                    y_offset = (SCREEN_HEIGHT - final_h) // 2
                    x_offset = (half_width - final_w) // 2
                    exact_size[y_offset:y_offset+final_h, x_offset:x_offset+final_w] = frame_cropped
                    frame_cropped = exact_size
                
                # Place in the correct half of the screen
                x_start = i * half_width
                background[:, x_start:x_start+half_width] = frame_cropped

            # Display the composite image with both camera feeds
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
            
            # Get original frame dimensions
            h, w = frame.shape[:2]
            
            # Calculate scaling factors - use full screen dimensions
            scale_w = SCREEN_WIDTH / w
            scale_h = SCREEN_HEIGHT / h
            scale = min(scale_w, scale_h)  # Maintain aspect ratio
            
            # Calculate new dimensions
            new_w = int(w * scale)
            new_h = int(h * scale)
            
            # Resize the frame
            frame = cv2.resize(frame, (new_w, new_h))
            
            # Create a black background image with screen dimensions
            background = np.zeros((SCREEN_HEIGHT, SCREEN_WIDTH, 3), dtype=np.uint8)
            
            # Calculate centering offsets
            x_offset = (SCREEN_WIDTH - new_w) // 2
            y_offset = (SCREEN_HEIGHT - new_h) // 2
            
            # Place the frame on the black background
            background[y_offset:y_offset+new_h, x_offset:x_offset+new_w] = frame
            
            # Display the result
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
    
    # Set up OpenCV window - keep this part
    cv2.namedWindow('Camera View', cv2.WINDOW_NORMAL)
    cv2.setWindowProperty('Camera View', cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)
    
    # Create a keyboard controller for the UI to send keypresses
    kb_controller = keyboard.Controller()
    
    # Define functions to send camera and fan commands
    def send_camera(key):
        kb_controller.press(key)
        kb_controller.release(key)
    
    def send_fan(key):
        kb_controller.press(key)
        kb_controller.release(key)
    
    # Start the UI overlay thread
    ui = UIOverlay(send_camera=send_camera, send_fan=send_fan)
    ui.start()
    
    # Continue with keyboard listener
    with keyboard.Listener(on_press=on_press, on_release=on_release) as listener:
        listener.join()

if __name__ == "__main__":
    main()
