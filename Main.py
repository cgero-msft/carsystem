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
import logging
import os
from datetime import datetime

##### LOGGING SETUP #####
# Create logs directory if it doesn't exist
log_dir = "/home/cgero88/logs"
os.makedirs(log_dir, exist_ok=True)

# Set up main logger
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(f"{log_dir}/carsystem_main.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("CarSystem")

# Camera-specific loggers
camera_loggers = {}
for cam_id in ['1', '2', '3']:
    cam_logger = logging.getLogger(f"Camera{cam_id}")
    cam_logger.setLevel(logging.INFO)
    handler = logging.FileHandler(f"{log_dir}/camera_{cam_id}.log")
    handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
    cam_logger.addHandler(handler)
    camera_loggers[cam_id] = cam_logger

# Create a stats logger for periodic stats
stats_logger = logging.getLogger("CameraStats")
stats_logger.setLevel(logging.INFO)
stats_handler = logging.FileHandler(f"{log_dir}/camera_stats.log")
stats_handler.setFormatter(logging.Formatter('%(asctime)s - %(message)s'))
stats_logger.addHandler(stats_handler)

##### CAMERA SECTION #####
# Camera name mapping for better logs
camera_names = {
    '1': 'Rowley',
    '2': 'Carson', 
    '3': 'Brevity'
}

# Track camera stats
camera_stats = {
    '1': {'frames_read': 0, 'frames_failed': 0, 'last_frame_time': None, 'start_time': None},
    '2': {'frames_read': 0, 'frames_failed': 0, 'last_frame_time': None, 'start_time': None},
    '3': {'frames_read': 0, 'frames_failed': 0, 'last_frame_time': None, 'start_time': None}
}

camera_paths = {
    '1': #direct
        #'/dev/v4l/by-path/platform-fd500000.pcie-pci-0000:01:00.0-usb-0:1.1:1.0-video-index0',
        #hub or sabrent
        '/dev/v4l/by-path/platform-fd500000.pcie-pci-0000:01:00.0-usb-0:1.1.4:1.0-video-index0',
    '2':#direct
        #'/dev/v4l/by-path/platform-fd500000.pcie-pci-0000:01:00.0-usb-0:1.3:1.0-video-index0',
        #hub
        #'/dev/v4l/by-path/platform-fd500000.pcie-pci-0000:01:00.0-usb-0:1.1.3:1.0-video-index0',
        #sabrent
        '/dev/v4l/by-path/platform-fd500000.pcie-pci-0000:01:00.0-usb-0:1.1.3:1.0-video-index0',
    '3': #direct
        #'/dev/v4l/by-path/platform-fd500000.pcie-pci-0000:01:00.0-usb-0:1.4:1.0-video-index0'
        #hub
        #'/dev/v4l/by-path/platform-fd500000.pcie-pci-0000:01:00.0-usb-0:1.1.2:1.0-video-index0'
        #sabrent
        '/dev/v4l/by-path/platform-fd500000.pcie-pci-0000:01:00.0-usb-0:1.1.1:1.0-video-index0'
        #'/dev/v4l/by-path/platform-fd500000.pcie-pci-0000:01:00.0-usb-0:1.1.1:1.0-video-index0'
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
    logger.info(f"Using fixed resolution: {SCREEN_WIDTH}x{SCREEN_HEIGHT}")
    return SCREEN_WIDTH, SCREEN_HEIGHT

# Use a global variable to store screen dimensions
SCREEN_WIDTH, SCREEN_HEIGHT = get_screen_resolution()

def get_single_frame(path):
    cap = cv2.VideoCapture(path)
    if not cap.isOpened():
        logger.error(f"Could not open {path}")
        return np.zeros((SCREEN_HEIGHT, SCREEN_WIDTH, 3), dtype=np.uint8)
    ret, frame = cap.read()
    cap.release()
    if not ret:
        return np.zeros((SCREEN_HEIGHT, SCREEN_WIDTH, 3), dtype=np.uint8)
    return cv2.resize(frame, (SCREEN_WIDTH, SCREEN_HEIGHT))

def show_multiview(cam_keys):
    global stop_thread, SCREEN_WIDTH, SCREEN_HEIGHT
    stop_thread = False
    logger.info(f"Showing multiview: Camera {camera_names[cam_keys[0]]} and Camera {camera_names[cam_keys[1]]}")

    # Ensure we have valid screen dimensions
    if SCREEN_WIDTH <= 0 or SCREEN_HEIGHT <= 0:
        logger.warning("Invalid screen dimensions, resetting to defaults")
        SCREEN_WIDTH, SCREEN_HEIGHT = 1024, 600

    def display():
        caps = []
        for k in cam_keys:
            camera_stats[k]['start_time'] = datetime.now()
            camera_stats[k]['frames_read'] = 0
            camera_stats[k]['frames_failed'] = 0
            
            camera_name = camera_names[k]
            camera_loggers[k].info(f"Opening camera {camera_name} at {camera_paths[k]}")
            
            try:
                cap = cv2.VideoCapture(camera_paths[k], cv2.CAP_V4L2)
                
                if not cap.isOpened():
                    camera_loggers[k].error(f"Failed to open camera {camera_name}")
                    cap = None
                else:
                    cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*'MJPG'))
                    cap.set(cv2.CAP_PROP_FPS, 30)
                    camera_loggers[k].info(f"Successfully opened camera {camera_name}, FPS set to 30")
                
                caps.append(cap)
            except Exception as e:
                camera_loggers[k].error(f"Exception opening camera {camera_name}: {str(e)}")
                caps.append(None)

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
        
        # Stats logging interval (every 30 seconds)
        last_stats_log = time.time()

        while not stop_thread:
            # Log camera stats periodically
            current_time = time.time()
            if current_time - last_stats_log > 30:  # Every 30 seconds
                for k in cam_keys:
                    uptime = "unknown"
                    if camera_stats[k]['start_time']:
                        uptime = str(datetime.now() - camera_stats[k]['start_time'])
                    
                    total_frames = camera_stats[k]['frames_read'] + camera_stats[k]['frames_failed']
                    failure_rate = 0
                    if total_frames > 0:
                        failure_rate = (camera_stats[k]['frames_failed'] / total_frames) * 100
                    
                    stats_logger.info(
                        f"Camera {camera_names[k]} stats: "
                        f"Uptime={uptime}, "
                        f"Frames read={camera_stats[k]['frames_read']}, "
                        f"Frames failed={camera_stats[k]['frames_failed']}, "
                        f"Failure rate={failure_rate:.2f}%, "
                        f"Time since last frame: {datetime.now() - camera_stats[k]['last_frame_time'] if camera_stats[k]['last_frame_time'] else 'N/A'}"
                    )
                last_stats_log = current_time
            
            # Create a fresh black background for each frame
            background = np.zeros((SCREEN_HEIGHT, SCREEN_WIDTH, 3), dtype=np.uint8)
            
            for i, (cap, k) in enumerate(zip(caps, cam_keys)):
                if cap is None:
                    camera_loggers[k].error(f"Camera {camera_names[k]} is None, cannot read frame")
                    camera_stats[k]['frames_failed'] += 1
                    continue
                    
                try:
                    ret, frame = cap.read()
                    
                    if not ret:
                        camera_stats[k]['frames_failed'] += 1
                        camera_loggers[k].warning(f"Camera {camera_names[k]} failed to read frame")
                        frame = np.zeros((480, 640, 3), dtype=np.uint8)
                    else:
                        camera_stats[k]['frames_read'] += 1
                        camera_stats[k]['last_frame_time'] = datetime.now()
                        
                        # Log occasional heartbeat for successful frames (every 300 frames ~10 seconds at 30fps)
                        if camera_stats[k]['frames_read'] % 300 == 0:
                            camera_loggers[k].info(
                                f"Camera {camera_names[k]} heartbeat: "
                                f"{camera_stats[k]['frames_read']} frames read, "
                                f"{camera_stats[k]['frames_failed']} frames failed"
                            )
                    
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

                except Exception as e:
                    camera_loggers[k].error(f"Exception processing frame from {camera_names[k]}: {str(e)}")
                    camera_stats[k]['frames_failed'] += 1
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

        for i, (cap, k) in enumerate(zip(caps, cam_keys)):
            if cap:
                try:
                    cap.release()
                    camera_loggers[k].info(f"Released camera {camera_names[k]}")
                except Exception as e:
                    camera_loggers[k].error(f"Error releasing camera {camera_names[k]}: {str(e)}")

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

    logger.info(f"Switching mode to: {mode}{' with cameras ' + ','.join([camera_names[k] for k in cam_keys]) if cam_keys else ''}")

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
        logger.info("Previous display thread terminated")

    current_mode = mode

    if mode == 'multi':
        display_thread = show_multiview(cam_keys)
    elif mode in ['1', '2', '3']:
        display_thread = show_single(mode)
    else:
        logger.error(f"Invalid mode: {mode}")
        return

    display_thread.start()
    logger.info(f"New display thread started for mode: {mode}")

##### FAN SECTION #####
i2c = busio.I2C(SCL, SDA)
pca = PCA9685(i2c)
pca.frequency = 250

# Create three fan channel objects
fans = {
    0: pca.channels[0],  # Fan 1
    1: pca.channels[1],  # Fan 2
    2: pca.channels[2]   # Fan 3
}

# Hex values for different duty cycles
DUTY_0   = 0x0000  # 0%
DUTY_33  = 0x5555  # 33%
DUTY_66  = 0xAAAA  # 66%
DUTY_100 = 0xFFFF  # 100%

# Map keys to (fan channel, duty cycle)
duty_lookup = {
    # Fan 1 (PCA channel 0)
    'a': (0, DUTY_0),    # 0%
    's': (0, DUTY_33),   # 33%
    'd': (0, DUTY_66),   # 66%
    'f': (0, DUTY_100),  # 100%
    
    # Fan 2 (PCA channel 1)
    'g': (1, DUTY_0),    # 0%
    'h': (1, DUTY_33),   # 33%
    'j': (1, DUTY_66),   # 66%
    'k': (1, DUTY_100),  # 100%
    
    # Fan 3 (PCA channel 2)
    'z': (2, DUTY_0),    # 0%
    'x': (2, DUTY_33),   # 33%
    'c': (2, DUTY_66),   # 66%
    'v': (2, DUTY_100)   # 100%
}

##### HOTKEYS #####
def on_press(key):
    global multiview_selection, current_mode

    try:
        if hasattr(key, 'char'):
            c = key.char.lower()

            # Fan control
            if c in duty_lookup:
                fan_index, duty = duty_lookup[c]
                fans[fan_index].duty_cycle = duty
                fan_name = f"Fan {fan_index+1}"
                percent = int((duty / 0xFFFF) * 100)
                print(f"[KEY '{c.upper()}'] → {fan_name} speed set to {percent}%")

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
        # Turn off all fans
        for fan in fans.values():
            fan.duty_cycle = 0x0000
        pca.deinit()
        global stop_thread
        stop_thread = True
        if display_thread and display_thread.is_alive():
            display_thread.join()
        return False  # This stops the keyboard listener

##### MAIN ENTRY POINT #####
def main():
    logger.info("Camera system starting up")
    logger.info("Hotkeys: 1/2/3 = Fullscreen view, 0 + two cameras = Multiview, A/S/D/F/G/H = Fan speed, ESC = Quit")

    # Auto-start in multiview mode with Cameras 3 and 1
    logger.info("Auto-starting in multiview mode with Brevity and Rowley cameras")
    switch_mode('multi', ['3', '1'])
    
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
