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
    def __init__(self, root, buttons, is_multiview=False):
        self.root = root
        self.overlay = tk.Toplevel(root)
        self.overlay.attributes('-fullscreen', True)
        self.overlay.attributes('-alpha', 0.7)
        self.overlay.attributes('-topmost', True)
        self.overlay.configure(bg='white')
        
        self.is_multiview = is_multiview
        self.selected_cameras = []
        self.buttons = {}
        
        # Create frame for buttons
        button_frame = tk.Frame(self.overlay, bg='white')
        button_frame.place(relx=0.5, rely=0.5, anchor='center')
        
        # Create label for multiview instructions
        if is_multiview:
            instructions = tk.Label(
                button_frame, 
                text="Select two cameras for multiview", 
                font=("Arial", 16, "bold"),
                bg="white"
            )
            instructions.pack(pady=10)
        
        # Create button frame for grid layout
        btn_container = tk.Frame(button_frame, bg='white')
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
                command=lambda c=cmd, t=text, b=None: self._handle_selection(c, t, b)
            )
            btn.grid(row=row, column=col, padx=10, pady=10)
            self.buttons[text] = btn
        
        # Add close button for multiview
        if is_multiview:
            close_btn = tk.Button(
                button_frame, 
                text="Cancel", 
                width=12, 
                height=2,
                font=("Arial", 12),
                bg="#777777",
                fg="white",
                command=self.destroy
            )
            close_btn.pack(pady=20)
        
        # Auto-destroy if not is_multiview
        if not is_multiview:
            self.overlay.after(5000, self.destroy)

    def _handle_selection(self, cmd, text, button):
        if not self.is_multiview:
            # Regular menu - execute and close
            cmd()
            self.destroy()
        else:
            # Multiview selection - track selections
            if text.startswith('Cam '):
                cam_num = text.split(' ')[1]
                
                # Toggle selection
                if cam_num in self.selected_cameras:
                    self.selected_cameras.remove(cam_num)
                    self.buttons[text].config(bg="SystemButtonFace")  # Reset to default color
                else:
                    # Add to selection if we have room
                    if len(self.selected_cameras) < 2:
                        self.selected_cameras.append(cam_num)
                        self.buttons[text].config(bg="#00A0FF")  # Highlight selected
                
                # If we have 2 selected, trigger multiview
                if len(self.selected_cameras) == 2:
                    self.root.after(500, self._trigger_multiview)
    
    def _trigger_multiview(self):
        # First send the multiview keystroke
        cmd = self.buttons['Multi'].cget('command')
        cmd()
        
        # Then send each camera keystroke
        for cam_num in self.selected_cameras:
            cam_btn_text = f'Cam {cam_num}'
            cmd = self.buttons[cam_btn_text].cget('command')
            cmd()
        
        # Finally close
        self.destroy()
    
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
            command=lambda: handle_button_press(camera_btn, self.show_camera_menu)
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

    def show_camera_menu(self):
        OverlayMenu(root, [
            ('Cam 1', lambda: self.send_camera('1')),
            ('Cam 2', lambda: self.send_camera('2')),
            ('Cam 3', lambda: self.send_camera('3')),
            ('Multi', lambda: self.start_multiview())
        ])

    def start_multiview(self):
        # Send the multiview keystroke '0'
        self.send_camera('0')
        
        # Show camera selection overlay
        OverlayMenu(root, [
            ('Cam 1', lambda: self.send_camera('1')),
            ('Cam 2', lambda: self.send_camera('2')),
            ('Cam 3', lambda: self.send_camera('3')),
        ], is_multiview=True)

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