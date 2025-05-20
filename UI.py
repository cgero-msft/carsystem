import tkinter as tk
import threading
import time
from pynput.keyboard import Controller, Key, Listener
import cv2, numpy as np
from board import SCL, SDA
import busio
from adafruit_pca9685 import PCA9685

# --- Your existing camera & fan code remains unchanged ---
# (Copy your entire background code: show_single, show_multiview, switch_mode, on_press, on_release, main)
# Ensure that `main()` launches the cv2 windows and listener.

# We'll wrap the UI in a separate thread that only handles overlays.

class OverlayMenu:
    def __init__(self, root, buttons):
        self.root = root
        self.overlay = tk.Toplevel(root)
        self.overlay.attributes('-fullscreen', True)
        self.overlay.attributes('-alpha', 0.7)
        self.overlay.attributes('-topmost', True)
        self.overlay.configure(bg='white')
        for idx, (text, cmd) in enumerate(buttons):
            btn = tk.Button(self.overlay, text=text, command=lambda c=cmd: self._select(c),
                            width=12, height=3)
            btn.place(relx=(idx+1)/(len(buttons)+1), rely=0.5, anchor='center')
        self.overlay.after(5000, self.destroy)

    def _select(self, cmd):
        cmd()
        self.destroy()

    def show(self): pass  # already visible on init
    def destroy(self):
        if self.overlay.winfo_exists():
            self.overlay.destroy()

class UIOverlay(threading.Thread):
    def __init__(self, send_camera, send_fan):
        super().__init__(daemon=True)
        self.send_camera = send_camera
        self.send_fan = send_fan

    def run(self):
        root = tk.Tk()
        root.overrideredirect(True)  # No window decorations
        root.attributes('-topmost', True)  # Keep on top
        
        # Create a small panel at the bottom center of the screen
        panel_width = 300
        panel_height = 60
        screen_width = root.winfo_screenwidth()
        screen_height = root.winfo_screenheight()
        
        # Position the panel at the bottom center
        root.geometry(f"{panel_width}x{panel_height}+{(screen_width-panel_width)//2}+{screen_height-panel_height-10}")
        
        # Make it semi-transparent and visible
        root.configure(bg='#333333')
        root.attributes('-alpha', 0.7)  # Semi-transparent
        
        # Function to handle button press with timed visual feedback
        def handle_button_press(button, command):
            # Execute the command
            command()
            
            # Visual feedback for 50ms
            original_bg = button.cget('bg')
            button.config(bg="#00A0FF")  # Brighter blue when pressed
            root.after(50, lambda: button.config(bg=original_bg))  # Return to normal after 50ms
        
        # Set equal width for both buttons
        button_width = 10
        
        # Camera button
        camera_btn = tk.Button(
            root, 
            text="Camera",
            bg="#0078D7",
            fg="white",
            font=("Arial", 12, "bold"),
            width=button_width,
            command=lambda: handle_button_press(camera_btn, lambda: OverlayMenu(root, [
                ('Cam 1', lambda: self.send_camera('1')),
                ('Cam 2', lambda: self.send_camera('2')),
                ('Cam 3', lambda: self.send_camera('3')),
                ('Multi', lambda: self.send_camera('0'))
            ]))
        )
        camera_btn.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Fan button with same width
        fan_btn = tk.Button(
            root, 
            text="Fan",
            bg="#0078D7", 
            fg="white",
            font=("Arial", 12, "bold"),
            width=button_width,
            command=lambda: handle_button_press(fan_btn, lambda: OverlayMenu(root, [
                ('0%', lambda: self.send_fan('a')),
                ('20%', lambda: self.send_fan('s')),
                ('40%', lambda: self.send_fan('d')),
                ('60%', lambda: self.send_fan('f')),
                ('80%', lambda: self.send_fan('g')),
                ('100%', lambda: self.send_fan('h'))
            ]))
        )
        fan_btn.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        root.mainloop()

if __name__=='__main__':
    # Start your cv2 camera+fan process in main thread
    cam_fan_thread = threading.Thread(target=main, daemon=True)
    cam_fan_thread.start()
    # Start the overlay UI
    ui = UIOverlay(
        send_camera=lambda c: Controller().press(c) or Controller().release(c),
        send_fan=lambda k: Controller().press(k) or Controller().release(k)
    )
    ui.start()
    cam_fan_thread.join()