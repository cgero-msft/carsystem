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
import os
import datetime
import logging
from logging.handlers import RotatingFileHandler
import fcntl
import v4l2
import select
import sys

##### CAMERA SECTION #####
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
    logging.info(f"Starting multiview mode with cameras: {cam_keys}")

    # Ensure we have valid screen dimensions
    if SCREEN_WIDTH <= 0 or SCREEN_HEIGHT <= 0:
        logging.warning(f"Invalid screen dimensions, resetting to defaults")
        SCREEN_WIDTH, SCREEN_HEIGHT = 1024, 600

    def display():
        caps = []
        last_frames = {}
        consecutive_errors = {k: 0 for k in cam_keys}
        consecutive_black = {k: 0 for k in cam_keys}
        consecutive_frozen = {k: 0 for k in cam_keys}
        frame_counts = {k: 0 for k in cam_keys}
        last_log_time = time.time()
        
        for i, k in enumerate(cam_keys):
            path = camera_paths[k]
            logging.info(f"Opening camera {k} from path: {path}")
            cap = cv2.VideoCapture(camera_paths[k], cv2.CAP_V4L2)
            cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*'MJPG'))
            cap.set(cv2.CAP_PROP_FPS, 30)
            
            if cap.isOpened():
                width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                fps = cap.get(cv2.CAP_PROP_FPS)
                logging.info(f"Camera {k} opened with resolution {width}x{height}, target FPS: {fps}")
            else:
                logging.error(f"Failed to open camera {k}")
            
            caps.append(cap)
            last_frames[k] = None

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
            # Log FPS every 5 seconds
            current_time = time.time()
            if current_time - last_log_time >= 5.0:
                elapsed = current_time - last_log_time
                for k in cam_keys:
                    fps = frame_counts[k] / elapsed if elapsed > 0 else 0
                    logging.info(f"Camera {k} (multiview): Processed {frame_counts[k]} frames in {elapsed:.2f}s ({fps:.2f} FPS)")
                    frame_counts[k] = 0
                last_log_time = current_time
            
            # Create a fresh black background for each frame
            background = np.zeros((SCREEN_HEIGHT, SCREEN_WIDTH, 3), dtype=np.uint8)
            
            for i, (cap, k) in enumerate(zip(caps, cam_keys)):
                frame_read_start = time.time()
                ret, frame = cap.read()
                frame_read_duration = time.time() - frame_read_start
                
                if frame_read_duration > 0.1:
                    logging.warning(f"Camera {k} (multiview): Slow frame read ({frame_read_duration:.3f}s)")
                
                if not ret:
                    consecutive_errors[k] += 1
                    if consecutive_errors[k] == 1 or consecutive_errors[k] % 10 == 0:
                        logging.error(f"Camera {k} (multiview): Failed to read frame. Consecutive errors: {consecutive_errors[k]}")
                    frame = np.zeros((480, 640, 3), dtype=np.uint8)
                else:
                    if consecutive_errors[k] > 0:
                        logging.info(f"Camera {k} (multiview): Frame reading resumed after {consecutive_errors[k]} errors")
                        consecutive_errors[k] = 0
                    frame_counts[k] += 1
                
                # Check for black frames
                if detect_black_frame(frame):
                    consecutive_black[k] += 1
                    if consecutive_black[k] == 1 or consecutive_black[k] % 10 == 0:
                        logging.warning(f"Camera {k} (multiview): Black frame detected. Consecutive: {consecutive_black[k]}")
                else:
                    if consecutive_black[k] > 0:
                        logging.info(f"Camera {k} (multiview): Normal frames resumed after {consecutive_black[k]} black frames")
                        consecutive_black[k] = 0
                
                # Check for frozen frames
                if last_frames[k] is not None and detect_frozen_frame(frame, last_frames[k]):
                    consecutive_frozen[k] += 1
                    if consecutive_frozen[k] == 1 or consecutive_frozen[k] % 10 == 0:
                        logging.warning(f"Camera {k} (multiview): Possible frozen frame. Consecutive: {consecutive_frozen[k]}")
                else:
                    if consecutive_frozen[k] > 0:
                        logging.info(f"Camera {k} (multiview): Frame changes detected after {consecutive_frozen[k]} possibly frozen frames")
                        consecutive_frozen[k] = 0
                
                last_frames[k] = frame.copy()
                
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

        logging.info(f"Multiview display thread stopping, releasing resources")
        for cap in caps:
            cap.release()

    return threading.Thread(target=display)

def show_single(cam_key):
    global stop_thread
    stop_thread = False
    
    logging.info(f"Starting single view mode for Camera {cam_key}")
    path = camera_paths[cam_key]
    
    # Log camera properties before opening
    logging.info(f"Opening camera {cam_key} from path: {path}")
    
    # Use V4L2 capture
    cap = cv2.VideoCapture(path, cv2.CAP_V4L2)
    
    # Set more robust capture parameters
    cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*'MJPG'))
    cap.set(cv2.CAP_PROP_FPS, 30)
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)  # Minimize buffering
    
    if not cap.isOpened():
        logging.error(f"Failed to open camera {cam_key} at path {path}")
        return None
    
    # Log camera properties
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = cap.get(cv2.CAP_PROP_FPS)
    logging.info(f"Camera {cam_key} opened with resolution {width}x{height}, target FPS: {fps}")
    
    # Flush the buffer by reading several frames
    for _ in range(5):
        ret, _ = cap.read()
        if not ret:
            break
    
    def display():
        frame_count = 0
        start_time = time.time()
        last_log_time = start_time
        last_frame = None
        consecutive_errors = 0
        consecutive_frozen = 0
        consecutive_black = 0
        
        while not stop_thread:
            # Log actual achieved FPS every 5 seconds
            current_time = time.time()
            if current_time - last_log_time >= 5.0:
                elapsed = current_time - last_log_time
                fps = frame_count / elapsed if elapsed > 0 else 0
                logging.info(f"Camera {cam_key}: Processed {frame_count} frames in {elapsed:.2f}s ({fps:.2f} FPS)")
                frame_count = 0
                last_log_time = current_time
            
            # Read frame with timeout detection
            frame_read_start = time.time()
            ret, frame = cap.read()
            frame_read_duration = time.time() - frame_read_start
            
            # Log frame reading performance
            if frame_read_duration > 0.1:  # Log slow reads
                logging.warning(f"Camera {cam_key}: Slow frame read ({frame_read_duration:.3f}s)")
            
            if not ret:
                consecutive_errors += 1
                if consecutive_errors == 1 or consecutive_errors % 10 == 0:
                    logging.error(f"Camera {cam_key}: Failed to read frame. Consecutive errors: {consecutive_errors}")
                time.sleep(0.1)
                continue
            else:
                if consecutive_errors > 0:
                    logging.info(f"Camera {cam_key}: Frame reading resumed after {consecutive_errors} errors")
                    consecutive_errors = 0
            
            # Check for black frames
            if detect_black_frame(frame):
                consecutive_black += 1
                if consecutive_black == 1 or consecutive_black % 10 == 0:
                    logging.warning(f"Camera {cam_key}: Black frame detected. Consecutive: {consecutive_black}")
            else:
                if consecutive_black > 0:
                    logging.info(f"Camera {cam_key}: Normal frames resumed after {consecutive_black} black frames")
                    consecutive_black = 0
            
            # Check for frozen frames
            if last_frame is not None and detect_frozen_frame(frame, last_frame):
                consecutive_frozen += 1
                if consecutive_frozen == 1 or consecutive_frozen % 10 == 0:
                    logging.warning(f"Camera {cam_key}: Possible frozen frame. Consecutive: {consecutive_frozen}")
            else:
                if consecutive_frozen > 0:
                    logging.info(f"Camera {cam_key}: Frame changes detected after {consecutive_frozen} possibly frozen frames")
                    consecutive_frozen = 0
            
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
                
            # Increment frame counter
            frame_count += 1
            last_frame = frame.copy()  # Store current frame for freeze detection
                
        logging.info(f"Camera {cam_key}: Display thread stopping, releasing resources")
        cap.release()

    return threading.Thread(target=display)

def switch_mode(mode, cam_keys=None):
    global current_mode, stop_thread, display_thread
    
    logging.info(f"Switching mode: {mode}" + (f" with cameras {cam_keys}" if cam_keys else ""))

    # Mark old thread for stopping
    stop_thread = True
    if display_thread and display_thread.is_alive():
        logging.info("Waiting for previous display thread to exit")
        # Show transitional frame
        black_bg = np.zeros((SCREEN_HEIGHT, SCREEN_WIDTH, 3), dtype=np.uint8)
        cv2.namedWindow('Camera View', cv2.WINDOW_NORMAL)
        cv2.setWindowProperty('Camera View', cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)
        cv2.imshow('Camera View', black_bg)
        cv2.waitKey(1)
        
        # Wait for thread to finish with timeout
        display_thread.join(timeout=2.0)
        if display_thread.is_alive():
            logging.warning("Thread didn't exit cleanly, forcing continuation")

    current_mode = mode

    # Reset cameras before starting new mode
    if mode == 'multi' and cam_keys:
        for key in cam_keys:
            if key in camera_paths:
                reset_camera(camera_paths[key])
    elif mode in ['1', '2', '3']:
        reset_camera(camera_paths[mode])
        
    # Small delay after reset
    time.sleep(0.5)

    # Start the new display mode
    if mode == 'multi':
        logging.info(f"Starting multiview display thread with cameras: {cam_keys}")
        display_thread = show_multiview(cam_keys)
    elif mode in ['1', '2', '3']:
        logging.info(f"Starting single view display thread for camera: {mode}")
        display_thread = show_single(mode)
    else:
        logging.warning(f"Unknown mode requested: {mode}")
        return

    display_thread.start()

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

##### LOGGING #####
# Add this function to set up logging
def setup_logging():
    """Set up logging to file and console"""
    # Create logs directory if it doesn't exist
    log_dir = "/home/cgero88/logs"
    os.makedirs(log_dir, exist_ok=True)
    
    # Create timestamped log file
    current_time = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = f"{log_dir}/camera_log_{current_time}.txt"
    
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(message)s',
        handlers=[
            RotatingFileHandler(log_file, maxBytes=10*1024*1024, backupCount=5),
            logging.StreamHandler()  # Also log to console
        ]
    )
    
    logging.info(f"Logging initialized. Writing to {log_file}")
    logging.info(f"Camera paths: {camera_paths}")
    return log_file

# Add frame quality monitoring functions
def detect_black_frame(frame, threshold=10):
    """Detect if a frame is mostly black (returns True if black)"""
    if frame is None:
        return True
    mean_value = np.mean(frame)
    is_black = mean_value < threshold
    if is_black:
        logging.warning(f"Detected black frame (mean value: {mean_value:.2f})")
    return is_black

def detect_frozen_frame(current, previous, threshold=10.0):  # Increased from 3.0 to 10.0
    """Detect if frame hasn't changed (returns True if frozen)"""
    if current is None or previous is None:
        return False
    
    # Calculate difference between frames
    diff = cv2.absdiff(current, previous)
    mean_diff = np.mean(diff)
    is_frozen = mean_diff < threshold
    
    # Only log if actually frozen, and reduce logging frequency
    if is_frozen and mean_diff < 2.0:  # Only log for very low differences
        logging.debug(f"Detected frozen frame (mean diff: {mean_diff:.2f})")
    return is_frozen

def reset_camera(cam_path):
    """Reset a camera by closing and reopening it with buffer flushing"""
    logging.info(f"Resetting camera at {cam_path}")
    
    try:
        # Open camera
        cap = cv2.VideoCapture(cam_path)
        if not cap.isOpened():
            logging.error(f"Failed to open camera at {cam_path} for reset")
            return
            
        # Configure for better performance
        cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*'MJPG'))
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)  # Minimize buffering
        
        # Flush the buffer by reading several frames
        for _ in range(5):
            ret, _ = cap.read()
            if not ret:
                break
        
        # Release and reopen
        cap.release()
        
        logging.info(f"Camera at {cam_path} has been reset")
    except Exception as e:
        logging.error(f"Error resetting camera: {e}")

def read_frame_with_timeout(cap, timeout=1.0):
    """Read a frame with timeout protection"""
    start_time = time.time()
    ret, frame = False, None
    
    try:
        ret, frame = cap.read()
        elapsed = time.time() - start_time
        
        if elapsed > 0.1:
            logging.warning(f"Slow frame read ({elapsed:.3f}s)")
            
        if elapsed > timeout:
            logging.error(f"Frame read timeout exceeded {timeout}s")
            return False, None
            
    except Exception as e:
        logging.error(f"Exception during frame read: {e}")
    
    return ret, frame

##### MAIN ENTRY POINT #####
def main():
    # Setup logging
    log_file = setup_logging()
    
    logging.info("🎥 Webcam viewer starting")
    logging.info("🕹️  Hotkeys:\n  - 1/2/3 = Fullscreen view\n  - 0 + two cameras = Multiview\n  - A/S/D/F/G/H = Fan speed\n  - ESC = Quit")
    
    # Log system info
    logging.info(f"Screen dimensions: {SCREEN_WIDTH}x{SCREEN_HEIGHT}")
    logging.info(f"Camera paths: {camera_paths}")

    # Auto-start in multiview mode with Cameras 3 and 1
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
    # Set up logging immediately on startup
    setup_logging()
    
    main()
