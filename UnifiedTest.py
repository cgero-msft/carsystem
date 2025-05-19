import cv2
import numpy as np
import threading
from pynput import keyboard
import time
from board import SCL, SDA
import busio
from adafruit_pca9685 import PCA9685
import tkinter as tk
from tkinter import ttk
from PIL import Image, ImageTk
import os

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

def get_screen_resolution():
    print(f"📺 Using fixed resolution: {SCREEN_WIDTH}x{SCREEN_HEIGHT}")
    return SCREEN_WIDTH, SCREEN_HEIGHT

# Use a global variable to store screen dimensions
SCREEN_WIDTH, SCREEN_HEIGHT = get_screen_resolution()

##### UI SECTION #####
class CameraUI(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Car Camera System")
        self.attributes("-fullscreen", True)
        
        # Configure grid
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=3)  # Camera view takes 2/3 of height
        self.grid_rowconfigure(1, weight=1)  # Controls take 1/3 of height
        
        # Variables
        self.current_mode = None
        self.multiview_selection = []
        self.is_multiview_select_mode = False
        self.camera_caps = {}
        self.photo_images = {}  # Keep references to avoid garbage collection
        
        # Create UI elements
        self.create_widgets()
        
        # Setup keyboard shortcuts
        self.bind("<Key>", self.handle_key)
        self.bind("<Escape>", self.quit_app)
        
    def create_widgets(self):
        # Camera display area (top 2/3)
        self.camera_frame = tk.Frame(self, bg="black", height=SCREEN_HEIGHT*2//3)
        self.camera_frame.grid(row=0, column=0, sticky="nsew")
        
        # Create camera views (initially hidden)
        self.single_view = tk.Label(self.camera_frame, bg="black")
        self.single_view.pack(expand=True, fill="both")
        self.single_view.pack_forget()
        
        # Multi-view setup (two side by side labels)
        self.multi_view_frame = tk.Frame(self.camera_frame, bg="black")
        self.left_view = tk.Label(self.multi_view_frame, bg="black")
        self.right_view = tk.Label(self.multi_view_frame, bg="black")
        self.left_view.pack(side="left", expand=True, fill="both")
        self.right_view.pack(side="left", expand=True, fill="both")
        self.multi_view_frame.pack(expand=True, fill="both")
        self.multi_view_frame.pack_forget()
        
        # Control panel (bottom 1/3)
        self.control_frame = tk.Frame(self, bg="#333333", height=SCREEN_HEIGHT//3)
        self.control_frame.grid(row=1, column=0, sticky="nsew")
        
        # Create a frame for the camera buttons in a grid layout
        self.camera_buttons_frame = tk.Frame(self.control_frame, bg="#333333")
        self.camera_buttons_frame.place(relx=0.16, rely=0.5, anchor="center")
        
        # Common button style parameters
        button_width = 50
        button_height = 50
        button_font = ("Arial", 14, "bold")
        button_params = {
            "font": button_font,
            "width": 4,
            "height": 1,
        }
        
        # Create 2x2 grid of camera buttons
        # Top row - Cameras 1 and 2
        self.cam1_btn = tk.Button(
            self.camera_buttons_frame, 
            text="1",
            bg="#0064C8", fg="white",
            activebackground="#0078F0", activeforeground="white",
            command=lambda: self.select_camera("1"),
            **button_params
        )
        self.cam1_btn.grid(row=0, column=0, padx=5, pady=5)
        
        self.cam2_btn = tk.Button(
            self.camera_buttons_frame, 
            text="2", 
            bg="#0064C8", fg="white",
            activebackground="#0078F0", activeforeground="white",
            command=lambda: self.select_camera("2"),
            **button_params
        )
        self.cam2_btn.grid(row=0, column=1, padx=5, pady=5)
        
        # Bottom row - Camera 3 and Multi
        self.cam3_btn = tk.Button(
            self.camera_buttons_frame, 
            text="3", 
            bg="#0064C8", fg="white",
            activebackground="#0078F0", activeforeground="white",
            command=lambda: self.select_camera("3"),
            **button_params
        )
        self.cam3_btn.grid(row=1, column=0, padx=5, pady=5)
        
        self.multi_btn = tk.Button(
            self.camera_buttons_frame, 
            text="Multi", 
            bg="#0064C8", fg="white",
            activebackground="#0078F0", activeforeground="white",
            command=self.start_multiview_select,
            **button_params
        )
        self.multi_btn.grid(row=1, column=1, padx=5, pady=5)
        
        # Fan control label
        self.fan_label = tk.Label(self.control_frame, text="Fan: 0%", font=("Arial", 12), bg="#333333", fg="white")
        self.fan_label.place(relx=0.5, rely=0.8, anchor="center")
        
        # Multiview selection prompt (initially hidden)
        self.multiview_prompt = tk.Label(
            self, 
            text="Select two cameras for multiview", 
            font=("Arial", 16, "bold"),
            bg="black", fg="white"
        )
        
    def select_camera(self, cam_key):
        """Handle camera selection"""
        if self.is_multiview_select_mode:
            if cam_key not in self.multiview_selection:
                self.multiview_selection.append(cam_key)
                print(f"✅ Selected Camera {cam_key}")
                
            if len(self.multiview_selection) == 2:
                self.switch_mode('multi', self.multiview_selection)
                self.multiview_selection = []
                self.is_multiview_select_mode = False
                self.multiview_prompt.place_forget()
        else:
            self.switch_mode(cam_key)
    
    def start_multiview_select(self):
        """Start multiview camera selection"""
        self.multiview_selection = []
        self.is_multiview_select_mode = True
        self.multiview_prompt.place(relx=0.5, rely=0.5, anchor="center")
        print("📺 Select two cameras for multiview")
    
    def update_camera_view(self):
        """Update camera view with latest frame"""
        try:
            if self.current_mode == 'multi':
                # Update both views for multiview
                for i, cam_key in enumerate(self.active_cameras):
                    ret, frame = self.camera_caps[cam_key].read()
                    if ret:
                        frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                        frame = self.resize_frame(frame, is_multiview=True)
                        self.photo_images[cam_key] = ImageTk.PhotoImage(image=Image.fromarray(frame))
                        if i == 0:
                            self.left_view.configure(image=self.photo_images[cam_key])
                        else:
                            self.right_view.configure(image=self.photo_images[cam_key])
            
            elif self.current_mode in ['1', '2', '3']:
                # Update single view
                cam_key = self.current_mode
                ret, frame = self.camera_caps[cam_key].read()
                if ret:
                    frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    frame = self.resize_frame(frame, is_multiview=False)
                    self.photo_images[cam_key] = ImageTk.PhotoImage(image=Image.fromarray(frame))
                    self.single_view.configure(image=self.photo_images[cam_key])
            
            # Continue update loop if not stopped
            if not stop_thread:
                self.after(30, self.update_camera_view)
                
        except Exception as e:
            print(f"Camera update error: {e}")
            self.after(100, self.update_camera_view)
    
    def resize_frame(self, frame, is_multiview=False):
        """Resize the frame for display"""
        h, w = frame.shape[:2]
        target_height = SCREEN_HEIGHT // 3 * 2  # Use 2/3 of screen height
        
        if is_multiview:
            # For multiview, use half the screen width
            target_width = SCREEN_WIDTH // 2
        else:
            target_width = SCREEN_WIDTH
        
        # Calculate scaling factors
        scale_w = target_width / w
        scale_h = target_height / h
        scale = min(scale_w, scale_h)  # Maintain aspect ratio
        
        # Calculate new dimensions
        new_w = int(w * scale)
        new_h = int(h * scale)
        
        # Resize the frame
        return cv2.resize(frame, (new_w, new_h))
    
    def switch_mode(self, mode, cam_keys=None):
        """Switch between camera modes"""
        global stop_thread
        
        # Stop existing camera threads
        stop_thread = True
        time.sleep(0.2)
        stop_thread = False
        
        # Close existing camera captures
        for cap in self.camera_caps.values():
            cap.release()
        self.camera_caps.clear()
        
        self.current_mode = mode
        
        # Hide all views
        self.single_view.pack_forget()
        self.multi_view_frame.pack_forget()
        
        if mode == 'multi':
            self.active_cameras = cam_keys
            # Open the selected cameras
            for cam_key in cam_keys:
                self.camera_caps[cam_key] = cv2.VideoCapture(camera_paths[cam_key], cv2.CAP_V4L2)
                self.camera_caps[cam_key].set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*'MJPG'))
                self.camera_caps[cam_key].set(cv2.CAP_PROP_FPS, 30)
            
            # Show multiview frame
            self.multi_view_frame.pack(expand=True, fill="both")
            print(f"📷 Showing multiview: Camera {cam_keys[0]} and Camera {cam_keys[1]}")
            
        elif mode in ['1', '2', '3']:
            # Open the selected camera
            self.camera_caps[mode] = cv2.VideoCapture(camera_paths[mode], cv2.CAP_V4L2)
            self.camera_caps[mode].set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*'MJPG'))
            self.camera_caps[mode].set(cv2.CAP_PROP_FPS, 30)
            
            # Show single view
            self.single_view.pack(expand=True, fill="both")
            print(f"🔎 Fullscreen view: Camera {mode}")
        
        # Start the update loop
        self.update_camera_view()
    
    def handle_key(self, event):
        """Handle keyboard shortcuts"""
        key = event.char.lower() if hasattr(event, 'char') and event.char else ''
        
        # Fan control
        if key in duty_lookup:
            duty = duty_lookup[key]
            fan.duty_cycle = duty
            percent = int((duty / 0xFFFF) * 100)
            print(f"[KEY '{key.upper()}'] → Fan speed set to {percent}%")
            self.fan_label.config(text=f"Fan: {percent}%")
        
        # Fullscreen camera mode
        elif key in ['1', '2', '3'] and not self.is_multiview_select_mode:
            self.switch_mode(key)
        
        # Enter multi-select mode
        elif key == '0':
            self.start_multiview_select()
        
        # Select cameras for multiview
        elif self.is_multiview_select_mode and key in ['1', '2', '3']:
            self.select_camera(key)
    
    def quit_app(self, event=None):
        """Clean up and exit application"""
        global stop_thread
        stop_thread = True
        
        # Stop all camera captures
        for cap in self.camera_caps.values():
            cap.release()
            
        # Turn off fan
        fan.duty_cycle = 0x0000
        pca.deinit()
        
        self.destroy()
        os._exit(0)  # Force exit to ensure all threads are terminated

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

##### MAIN ENTRY POINT #####
def main():
    print("🎥 Webcam viewer ready")
    print("🕹️  Hotkeys:\n  - 1/2/3 = Fullscreen view\n  - 0 + two cameras = Multiview\n  - A/S/D/F/G/H = Fan speed\n  - ESC = Quit")
    
    app = CameraUI()
    # Auto-start in multiview mode with Cameras 1 and 2
    app.after(100, lambda: app.switch_mode('multi', ['1', '2']))
    app.mainloop()

if __name__ == "__main__":
    main()

