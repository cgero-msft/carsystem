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
        
        # Dark background color
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
        
        # Check if this is a fan control menu (has 20 buttons in 4 rows of 5)
        is_fan_grid = len(buttons) == 20
        
        if is_fan_grid:
            # Fan control grid layout (4 rows × 5 columns)
            for idx, (text, cmd) in enumerate(buttons):
                row = idx // 5
                col = idx % 5
                
                if col == 0:  # Fan names on the left
                    # Fan name label (left column)
                    lbl = tk.Label(
                        btn_container,
                        text=text,
                        font=("Arial", 12, "bold"),
                        width=10,
                        bg="#333333",
                        fg="white"
                    )
                    lbl.grid(row=row, column=col, padx=5, pady=5, sticky="nsew")
                else:
                    # Speed button
                    btn = tk.Button(
                        btn_container, 
                        text=text, 
                        width=8, 
                        height=2,
                        font=("Arial", 11),
                        # Darker button style
                        bg="#444444",
                        fg="white",
                        activebackground="#555555",
                        activeforeground="white",
                        command=lambda c=cmd, t=text: self._handle_selection(c, t)
                    )
                    btn.grid(row=row, column=col, padx=5, pady=5)
                    self.buttons[f"{row}-{col}"] = btn
        else:
            # Regular grid layout
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
        # Camera name to number mapping
        camera_mapping = {
            'Rowley': '1',
            'Glow': '2',
            'Brevity': '3'
        }
        
        if text == 'Multi':
            # Enter multiview selection mode
            self.multi_mode = True
            self.selected_cameras = []
            self.buttons['Multi'].config(bg="#00A0FF")  # Highlight Multi button
            
            # Update instructions
            self.title_label.config(text="Select two cameras for multiview")
            
            # Reset the auto-destroy timer
            self.overlay.after_cancel(self.timer_id)
            
            # First, send the multiview keystroke '0'
            cmd()
            
            return  # Don't close the menu yet
            
        elif self.multi_mode and text in camera_mapping:
            # We're in multiview mode and selecting cameras
            cam_num = camera_mapping[text]  # Get camera number from name
            
            if cam_num in self.selected_cameras:
                # Deselect camera
                self.selected_cameras.remove(cam_num)
                self.buttons[text].config(bg="#444444")  # Reset to dark button color
            else:
                # Select camera if we have room
                if len(self.selected_cameras) < 2:
                    self.selected_cameras.append(cam_num)
                    self.buttons[text].config(bg="#00A0FF")
            
            # If we selected two cameras, send the keystrokes and close
            if len(self.selected_cameras) == 2:
                # Send the camera keystrokes
                for cam_num in self.selected_cameras:
                    self.send_camera(cam_num)
                
                # Close menu after a short delay
                self.overlay.after(500, self.destroy)
                
            return
            
        else:
            # Normal mode - execute command and close
            cmd()
            self.destroy()
        
    # Add this method to OverlayMenu class
    def send_camera(self, number):
        """Send camera selection keypress"""
        # This forwards to the parent UIOverlay
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

    def show_fan_menu(self):
        print("Fan button clicked")  # Debug print
        
        # Create a grid of buttons with fan names on left and speeds across
        buttons = []
        
        # Add Rowley (Fan 1) row
        buttons.append(('Rowley', lambda: None))  # Fan name (no action)
        buttons.append(('Off', lambda: self.send_fan('a')))
        buttons.append(('Low', lambda: self.send_fan('s')))
        buttons.append(('Medium', lambda: self.send_fan('d')))
        buttons.append(('High', lambda: self.send_fan('f')))
        
        # Add Glow (Fan 2) row
        buttons.append(('Glow', lambda: None))
        buttons.append(('Off', lambda: self.send_fan('g')))
        buttons.append(('Low', lambda: self.send_fan('h')))
        buttons.append(('Medium', lambda: self.send_fan('j')))
        buttons.append(('High', lambda: self.send_fan('k')))
        
        # Add Brevity (Fan 3) row
        buttons.append(('Brevity', lambda: None))
        buttons.append(('Off', lambda: self.send_fan('z')))
        buttons.append(('Low', lambda: self.send_fan('x')))
        buttons.append(('Medium', lambda: self.send_fan('c')))
        buttons.append(('High', lambda: self.send_fan('v')))
        
        # Add ALL row
        buttons.append(('ALL', lambda: None))
        buttons.append(('Off', lambda: self.all_fans_speed('off')))
        buttons.append(('Low', lambda: self.all_fans_speed('low')))
        buttons.append(('Medium', lambda: self.all_fans_speed('medium')))
        buttons.append(('High', lambda: self.all_fans_speed('high')))
        
        OverlayMenu(self.root, buttons, title="Fan Control")

    def all_fans_speed(self, speed):
        """Set all fans to the specified speed."""
        if speed == 'off':
            self.send_fan('a')  # Fan 1 off
            self.send_fan('g')  # Fan 2 off
            self.send_fan('z')  # Fan 3 off
        elif speed == 'low':
            self.send_fan('s')  # Fan 1 low
            self.send_fan('h')  # Fan 2 low
            self.send_fan('x')  # Fan 3 low
        elif speed == 'medium':
            self.send_fan('d')  # Fan 1 medium
            self.send_fan('j')  # Fan 2 medium
            self.send_fan('c')  # Fan 3 medium
        elif speed == 'high':
            self.send_fan('f')  # Fan 1 high
            self.send_fan('k')  # Fan 2 high
            self.send_fan('v')  # Fan 3 high

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