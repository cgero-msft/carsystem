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
    def __init__(self, root, buttons, title="Select Option"):
        self.root = root
        self.overlay = tk.Toplevel(root)
        self.overlay.attributes('-fullscreen', True)
        self.overlay.attributes('-alpha', 0.7)
        self.overlay.attributes('-topmost', True)
        
        # Changed: Dark background color
        self.overlay.configure(bg='#222222')
        
        self.multi_mode = False
        self.selected_cameras = []
        self.buttons = {}
        
        # Create frame for buttons with dark background
        button_frame = tk.Frame(self.overlay, bg='#222222')
        button_frame.place(relx=0.5, rely=0.5, anchor='center')
        
        # Create title/instructions label with light text on dark background
        self.title_label = tk.Label(
            button_frame, 
            text=title, 
            font=("Arial", 16, "bold"),
            bg="#222222",
            fg="white"  # White text
        )
        self.title_label.pack(pady=10)
        
        # Create button frame for grid layout with dark background
        btn_container = tk.Frame(button_frame, bg='#222222')
        btn_container.pack()
        
        # Create buttons
        columns = min(4, len(buttons))
        for idx, (text, cmd) in enumerate(buttons):
            row = idx // columns
            col = idx % columns
            
            btn = tk.Button(
                btn_container, 
                text=text, 
                width=12, 
                height=3,
                font=("Arial", 12),
                # Darker button style
                bg="#444444",
                fg="white",
                activebackground="#555555",
                activeforeground="white",
                command=lambda c=cmd, t=text: self._handle_selection(c, t)
            )
            btn.grid(row=row, column=col, padx=10, pady=10)
            self.buttons[text] = btn
        
        # Add close button with darker style
        close_btn = tk.Button(
            button_frame, 
            text="Cancel", 
            width=12, 
            height=2,
            font=("Arial", 12),
            bg="#555555",
            fg="white",
            activebackground="#666666",
            activeforeground="white",
            command=self.destroy
        )
        close_btn.pack(pady=20)
        
        # Auto-destroy timer
        self.timer_id = self.overlay.after(5000, self.destroy)

    def _handle_selection(self, cmd, text):
        # MULTIVIEW SELECTION LOGIC
        if text == 'Multi':
            # Enter multiview selection mode
            self.multi_mode = True
            self.selected_cameras = []
            self.buttons['Multi'].config(bg="#00A0FF")  # Highlight button
            self.title_label.config(text="Select two cameras for multiview")
            self.overlay.after_cancel(self.timer_id)  # Cancel auto-close
            return  # Don't proceed further
            
        # CAMERA SELECTION IN MULTIVIEW MODE    
        elif self.multi_mode and text.startswith('Cam '):
            cam_num = text.split(' ')[1]
            
            # Toggle selection
            if cam_num in self.selected_cameras:
                self.selected_cameras.remove(cam_num)
                self.buttons[text].config(bg="#444444")  # Reset color
            else:
                # Add to selection if we have room
                if len(self.selected_cameras) < 2:
                    self.selected_cameras.append(cam_num)
                    self.buttons[text].config(bg="#00A0FF")  # Highlight
            
            # Only trigger when we have exactly 2 cameras selected
            if len(self.selected_cameras) == 2:
                # First send multiview keystroke '0'
                self.root._uioverlay.send_camera('0')
                
                # Then send camera keystrokes with delay
                def send_sequential():
                    for cam_num in self.selected_cameras:
                        self.root._uioverlay.send_camera(cam_num)
                        time.sleep(0.1)  # Small delay between keys
                    self.destroy()  # Close menu after sending all keys
                    
                # Schedule the sequential sending with a short delay
                self.overlay.after(200, send_sequential)
            
            return  # Important! Don't fall through to the default case
            
        # DEFAULT: NORMAL BUTTON CLICK
        else:
            # Normal mode - execute command and close
            cmd()
            self.destroy()
        
    # Add this method to OverlayMenu class
    def send_camera(self, number):
        """Send camera selection keypress"""
        # This just forwards to the parent UIOverlay
        if hasattr(self.root, '_uioverlay'):
            self.root._uioverlay.send_camera(number)

    def destroy(self):
        if self.overlay.winfo_exists():
            self.overlay.destroy()

class UIOverlay(threading.Thread):
    def __init__(self, send_camera, send_fan):
        super().__init__(daemon=True)
        self.send_camera = send_camera
        self.send_fan = send_fan
        self.root = None

    def run(self):
        self.root = tk.Tk()
        # Store reference to self for callbacks
        self.root._uioverlay = self  
        self.root.overrideredirect(True)
        self.root.attributes('-topmost', True)
        
        # Panel dimensions
        panel_width = 300
        panel_height = 60
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        
        # Position at bottom center
        self.root.geometry(f"{panel_width}x{panel_height}+{(screen_width-panel_width)//2}+{screen_height-panel_height-10}")
        
        # Semi-transparent background
        self.root.configure(bg='#333333')
        self.root.attributes('-alpha', 0.7)
        
        # Equal width buttons
        button_width = 10
        
        # SIMPLIFIED: Direct command binding without the wrapper
        camera_btn = tk.Button(
            self.root, 
            text="Camera",
            bg="#0078D7",
            fg="white",
            font=("Arial", 12, "bold"),
            width=button_width
        )
        # Bind click event directly
        camera_btn.config(command=self.show_camera_menu)
        camera_btn.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Fan button (same direct binding)
        fan_btn = tk.Button(
            self.root, 
            text="Fan",
            bg="#0078D7", 
            fg="white",
            font=("Arial", 12, "bold"),
            width=button_width
        )
        # Bind click event directly
        fan_btn.config(command=self.show_fan_menu)
        fan_btn.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        self.root.mainloop()

    # Separate method for showing fan menu
    def show_fan_menu(self):
        print("Fan button clicked")  # Debug print
        OverlayMenu(self.root, [
            ('0%', lambda: self.send_fan('a')),
            ('20%', lambda: self.send_fan('s')),
            ('40%', lambda: self.send_fan('d')),
            ('60%', lambda: self.send_fan('f')),
            ('80%', lambda: self.send_fan('g')),
            ('100%', lambda: self.send_fan('h'))
        ])

    def show_camera_menu(self):
        print("Camera button clicked")  # Debug print
        OverlayMenu(self.root, [
            ('Rowley', lambda: self.send_camera('1')),
            ('Glow', lambda: self.send_camera('2')),
            ('Brevity', lambda: self.send_camera('3')),
            ('Multi', lambda: self.send_camera('0'))
        ], title="Select Camera")

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