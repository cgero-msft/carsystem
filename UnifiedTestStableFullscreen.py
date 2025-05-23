import cv2
import numpy as np
import threading
import time
from pynput import keyboard
import tkinter as tk
import os
import subprocess
import sys

# Add more detailed print statements for troubleshooting
print("Starting application...")

try:
    from board import SCL, SDA
    import busio
    from adafruit_pca9685 import PCA9685
    from UI import UIOverlay
    print("Successfully imported all modules")
except ImportError as e:
    print(f"Import error: {e}")
    sys.exit(1)

# Simplified hide cursor function
def hide_cursor_system_wide():
    try:
        subprocess.call(['killall', 'unclutter'], stderr=subprocess.DEVNULL)
        subprocess.Popen(['unclutter', '-idle', '0'])
        print("Applied cursor hiding")
    except Exception as e:
        print(f"Cursor hiding error (non-fatal): {e}")

print("Setting up camera paths...")
camera_paths = {
    '1': '/dev/v4l/by-path/platform-fd500000.pcie-pci-0000:01:00.0-usb-0:1.1.4:1.0-video-index0',
    '2': '/dev/v4l/by-path/platform-fd500000.pcie-pci-0000:01:00.0-usb-0:1.1.3:1.0-video-index0',
    '3': '/dev/v4l/by-path/platform-fd500000.pcie-pci-0000:01:00.0-usb-0:1.1.2:1.0-video-index0'
}

# Global variables
current_mode = None
stop_thread = False
display_thread = None
multiview_selection = []

# Screen dimensions
SCREEN_WIDTH = 1024
SCREEN_HEIGHT = 600
print(f"📺 Using fixed resolution: {SCREEN_WIDTH}x{SCREEN_HEIGHT}")

print("Creating camera functions...")
def show_multiview(cam_keys):
    global stop_thread, SCREEN_WIDTH, SCREEN_HEIGHT
    stop_thread = False
    print(f"📷 Showing multiview: Camera {cam_keys[0]} and Camera {cam_keys[1]}")
    
    def display():
        caps = []
        try:
            # First create window early to prevent hanging
            window_name = 'Camera View'
            cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)
            cv2.setWindowProperty(window_name, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)
            
            # Display a "Loading..." message while cameras initialize
            loading_frame = np.zeros((SCREEN_HEIGHT, SCREEN_WIDTH, 3), dtype=np.uint8)
            font = cv2.FONT_HERSHEY_SIMPLEX
            cv2.putText(loading_frame, 'Loading cameras...', (SCREEN_WIDTH//4, SCREEN_HEIGHT//2), 
                      font, 1.5, (255, 255, 255), 2)
            cv2.imshow(window_name, loading_frame)
            cv2.waitKey(1)
            
            # Open cameras with timeout handling
            for k in cam_keys:
                try:
                    print(f"Opening camera {k}...")
                    # First try with default settings
                    cap = cv2.VideoCapture(camera_paths[k])
                    
                    # Important: Set camera properties AFTER opening
                    cap.set(cv2.CAP_PROP_BUFFERSIZE, 3)  # Use a small buffer
                    cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*'MJPG'))
                    cap.set(cv2.CAP_PROP_FPS, 15)  # Lower FPS for stability
                    
                    # Verify opening with timeout
                    start_time = time.time()
                    while not cap.isOpened() and time.time() - start_time < 5:
                        print(f"Retrying camera {k}...")
                        cap.release()
                        time.sleep(0.5)
                        cap = cv2.VideoCapture(camera_paths[k])
                    
                    if cap.isOpened():
                        # Test read a frame to make sure it works
                        ret, test_frame = cap.read()
                        if ret:
                            caps.append(cap)
                            print(f"Camera {k} initialized successfully")
                        else:
                            print(f"Camera {k} opened but could not read frame")
                            cap.release()
                    else:
                        print(f"Failed to open camera {k}")
                except Exception as e:
                    print(f"Error opening camera {k}: {e}")
            
            if not caps:
                print("No cameras could be initialized!")
                black_frame = np.zeros((SCREEN_HEIGHT, SCREEN_WIDTH, 3), dtype=np.uint8)
                cv2.putText(black_frame, 'ERROR: No cameras available', 
                          (SCREEN_WIDTH//4, SCREEN_HEIGHT//2), font, 1.5, (0, 0, 255), 2)
                cv2.imshow(window_name, black_frame)
                cv2.waitKey(1000)
                return

            # Calculate half width
            half_width = SCREEN_WIDTH // 2
            
            # Set up window to exact size
            cv2.moveWindow(window_name, 0, 0)
            cv2.resizeWindow(window_name, SCREEN_WIDTH, SCREEN_HEIGHT)
            
            print("Multiview started successfully")
            
            # Variables for FPS management and timeout detection
            frame_count = 0
            last_frame_time = time.time()
            
            while not stop_thread:
                # Create background
                background = np.zeros((SCREEN_HEIGHT, SCREEN_WIDTH, 3), dtype=np.uint8)
                
                # Process each camera
                frame_updated = False
                for i, cap in enumerate(caps):
                    # Use a timeout for reading frames
                    try:
                        ret, frame = cap.read()
                        if not ret:
                            # Show error indicator on this panel
                            x_start = i * half_width
                            cv2.putText(background, f"Camera {cam_keys[i]} error", 
                                     (x_start + 10, SCREEN_HEIGHT//2), font, 1, (0, 0, 255), 2)
                            continue
                        
                        # Resize frame to fit half screen
                        frame_resized = cv2.resize(frame, (half_width, SCREEN_HEIGHT))
                        
                        # Place in correct half
                        x_start = i * half_width
                        background[:, x_start:x_start+half_width] = frame_resized
                        frame_updated = True
                        last_frame_time = time.time()
                        frame_count += 1
                    except Exception as e:
                        print(f"Error reading from camera {i}: {e}")
                
                # Check for timeouts
                if time.time() - last_frame_time > 3.0:
                    print("Camera timeout detected - attempting recovery...")
                    # Try to recover cameras
                    for cap in caps:
                        cap.release()
                    caps = []
                    
                    # Reopen cameras
                    for k in cam_keys:
                        try:
                            cap = cv2.VideoCapture(camera_paths[k])
                            if cap.isOpened():
                                caps.append(cap)
                        except:
                            pass
                    
                    if not caps:
                        print("Camera recovery failed")
                    else:
                        print("Cameras recovered")
                    
                    # Reset timer
                    last_frame_time = time.time()
                
                # Show the combined image
                if frame_updated:
                    cv2.imshow(window_name, background)
                
                # Limit the UI refresh rate to reduce CPU load
                key = cv2.waitKey(30) & 0xFF  # 30ms delay (~33 FPS max)
                if key == ord('q'):
                    break
                    
            # Clean up
            for cap in caps:
                cap.release()
                
        except Exception as e:
            print(f"Error in multiview: {e}")
            # Clean up any partially initialized resources
            for cap in caps:
                try:
                    cap.release()
                except:
                    pass
    
    return threading.Thread(target=display)

def show_single(cam_key):
    global stop_thread
    stop_thread = False
    print(f"🔎 Fullscreen view: Camera {cam_key}")
    
    def display():
        try:
            # Open camera
            cap = cv2.VideoCapture(camera_paths[cam_key])
            if not cap.isOpened():
                print(f"Failed to open camera {cam_key}")
                return
                
            # Create window
            window_name = 'Camera View'
            cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)
            cv2.moveWindow(window_name, 0, 0)
            cv2.resizeWindow(window_name, SCREEN_WIDTH, SCREEN_HEIGHT)
            cv2.setWindowProperty(window_name, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)
            
            # Black image for initialization
            black = np.zeros((SCREEN_HEIGHT, SCREEN_WIDTH, 3), dtype=np.uint8)
            cv2.imshow(window_name, black)
            cv2.waitKey(1)
            
            print(f"Camera {cam_key} view started successfully")
            
            while not stop_thread:
                ret, frame = cap.read()
                if not ret:
                    time.sleep(0.1)
                    continue
                    
                # Resize to fit screen
                frame_resized = cv2.resize(frame, (SCREEN_WIDTH, SCREEN_HEIGHT))
                
                # Display
                cv2.imshow(window_name, frame_resized)
                if cv2.waitKey(1) & 0xFF == ord('q'):
                    break
                    
            # Clean up
            cap.release()
            
        except Exception as e:
            print(f"Error in single view: {e}")
    
    return threading.Thread(target=display)

print("Setting up switching function...")
def switch_mode(mode, cam_keys=None):
    global current_mode, stop_thread, display_thread
    print(f"Switching to mode: {mode}")
    
    # Create a black frame to prevent flashing
    try:
        black = np.zeros((SCREEN_HEIGHT, SCREEN_WIDTH, 3), dtype=np.uint8)
        cv2.namedWindow('Camera View', cv2.WINDOW_NORMAL)
        cv2.setWindowProperty('Camera View', cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)
        cv2.imshow('Camera View', black)
        cv2.waitKey(1)
    except Exception as e:
        print(f"Error showing black frame: {e}")
    
    # Stop existing thread
    stop_thread = True
    if display_thread and display_thread.is_alive():
        try:
            print("Waiting for previous thread to end...")
            display_thread.join(timeout=1.0)
        except Exception as e:
            print(f"Error stopping thread: {e}")
    
    current_mode = mode

    # Start new thread
    try:
        if mode == 'multi':
            display_thread = show_multiview(cam_keys)
        elif mode in ['1', '2', '3']:
            display_thread = show_single(mode)
        else:
            print(f"Unknown mode: {mode}")
            return
            
        print("Starting new camera thread...")
        display_thread.start()
    except Exception as e:
        print(f"Error starting thread: {e}")

print("Setting up I2C and PCA9685...")
try:
    i2c = busio.I2C(SCL, SDA)
    pca = PCA9685(i2c)
    pca.frequency = 250

    # Create fan channel objects
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
    print("PCA9685 setup complete")
except Exception as e:
    print(f"Error setting up PCA9685: {e}")
    # Continue without fan control

print("Setting up keyboard controls...")
def on_press(key):
    global multiview_selection, current_mode

    try:
        if hasattr(key, 'char'):
            c = key.char.lower()

            # Fan control
            if c in duty_lookup:
                fan_index, duty = duty_lookup[c]
                fans[fan_index].duty_cycle = duty

            # Fullscreen camera mode
            elif c in ['1', '2', '3'] and current_mode != 'multi_select':
                switch_mode(c)

            # Enter multi-select mode
            elif c == '0':
                print("📺 Entering multi-select mode")
                multiview_selection = []
                current_mode = 'multi_select'

            # Select cameras for multiview
            elif current_mode == 'multi_select' and c in ['1', '2', '3']:
                if c not in multiview_selection:
                    multiview_selection.append(c)
                if len(multiview_selection) == 2:
                    switch_mode('multi', multiview_selection)
                    multiview_selection = []
    except Exception as e:
        print(f"Keyboard error: {e}")

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
        return False  # Stop listener

print("Starting main program...")
def main():
    print("🎥 Webcam viewer ready")
    print("🕹️  Hotkeys:\n  - 1/2/3 = Fullscreen view\n  - 0 + two cameras = Multiview\n  - A/S/D/F/G/H = Fan speed\n  - ESC = Quit")
    
    # Hide cursor
    hide_cursor_system_wide()
    
    # Start with multiview mode
    try:
        print("Setting up initial camera view...")
        switch_mode('multi', ['1', '2'])
    except Exception as e:
        print(f"Error setting up initial view: {e}")
    
    # Set up keyboard controller
    kb_controller = keyboard.Controller()
    
    # Define functions for UI
    def send_camera(key):
        kb_controller.press(key)
        kb_controller.release(key)
    
    def send_fan(key):
        kb_controller.press(key)
        kb_controller.release(key)
    
    # Start the UI overlay
    try:
        print("Starting UI overlay...")
        ui = UIOverlay(send_camera=send_camera, send_fan=send_fan)
        ui.start()
    except Exception as e:
        print(f"Error starting UI: {e}")
    
    # Set up keyboard listener
    try:
        print("Starting keyboard listener...")
        with keyboard.Listener(on_press=on_press, on_release=on_release) as listener:
            listener.join()
    except Exception as e:
        print(f"Keyboard listener error: {e}")

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"Fatal error: {e}")
