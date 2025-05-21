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
        
        # Hide the main menu when opening this overlay
        if hasattr(root, '_uioverlay'):
            root._uioverlay.hide_main_menu()
            
        # Dark background color
        self.overlay.configure(bg='#222222')
        
        self.multi_mode = False
        self.selected_cameras = []
        self.buttons = {}
        
        # Add a flag to identify this as a fan control menu
        self.is_fan_menu = title == "Fan Control"
        
        # Create frame for buttons with dark background
        button_frame = tk.Frame(self.overlay, bg='#222222')
        
        # Check if this is a fan control menu with grid layout
        is_fan_grid = len(buttons) == 20
        
        # Position the button frame higher for fan control grid
        if is_fan_grid:
            # For Fan Control, place frame higher (40% down instead of 50%)
            button_frame.place(relx=0.5, rely=0.4, anchor='center')
        else:
            # Standard position for other menus
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
                    # Fan name label (left column) - make wider and taller
                    lbl = tk.Label(
                        btn_container,
                        text=text,
                        font=("Arial", 14, "bold"),  # Larger font
                        width=12,  # Wider
                        bg="#333333",
                        fg="white"
                    )
                    lbl.grid(row=row, column=col, padx=8, pady=8, sticky="nsew")
                else:
                    # Speed button - make 2x bigger
                    btn = tk.Button(
                        btn_container, 
                        text=text, 
                        width=16,  # 2x wider
                        height=4,  # 2x taller
                        font=("Arial", 13),
                        # Match hover colors to regular colors
                        bg="#444444",
                        fg="white",
                        activebackground="#444444",  # Same as bg
                        activeforeground="white",    # Same as fg
                        command=lambda c=cmd, t=text: self._handle_selection(c, t)
                    )
                    btn.grid(row=row, column=col, padx=8, pady=8)  # More padding
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
                    # Match hover colors to regular colors
                    bg="#444444",
                    fg="white",
                    activebackground="#444444",  # Same as bg
                    activeforeground="white",    # Same as fg
                    command=lambda c=cmd, t=text: self._handle_selection(c, t)
                )
                btn.grid(row=row, column=col, padx=10, pady=10)
                self.buttons[text] = btn
        
        # Add close button with darker style
        close_btn = tk.Button(
            self.overlay,  # Parent is the fullscreen overlay
            text="Cancel", 
            width=12, 
            height=2,
            font=("Arial", 12),
            bg="#555555",
            fg="white",
            activebackground="#555555",  # Same as bg
            activeforeground="white",    # Same as fg
            command=self.destroy
        )
        # Position at bottom left corner with some padding
        close_btn.place(x=20, rely=0.95, anchor='sw')
        
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
            
        # NEW: Special handling for fan speed buttons
        elif self.is_fan_menu and text in ['Off', 'Low', 'Medium', 'High']:
            # Execute the command
            cmd()
            
            # Reset the auto-destroy timer to keep menu open
            self.overlay.after_cancel(self.timer_id)
            self.timer_id = self.overlay.after(5000, self.destroy)
            
            # Update button highlighting - get the parent UIOverlay
            if hasattr(self.root, '_uioverlay'):
                self.root._uioverlay._highlight_active_fan_buttons(self)
            
            return  # Don't destroy the menu
            
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
        # Show the main menu again when closing this overlay
        if hasattr(self.root, '_uioverlay'):
            self.root._uioverlay.show_main_menu()
            
        if self.overlay.winfo_exists():
            self.overlay.destroy()

class UIOverlay(threading.Thread):
    def __init__(self, send_camera, send_fan):
        super().__init__(daemon=True)
        self.send_camera = send_camera
        self.send_fan = send_fan
        self.root = None
        
        # Track current fan states (initially all Off)
        self.fan_states = {
            'Rowley': 'Off',   # Fan 1
            'Glow': 'Off',     # Fan 2 
            'Brevity': 'Off'   # Fan 3
        }

    # Original send_fan wrapper to track states
    def _update_fan_state(self, key):
        # Map key to fan name and speed
        key_mapping = {
            'a': ('Rowley', 'Off'),
            's': ('Rowley', 'Low'),
            'd': ('Rowley', 'Medium'),
            'f': ('Rowley', 'High'),
            'g': ('Glow', 'Off'),
            'h': ('Glow', 'Low'),
            'j': ('Glow', 'Medium'),
            'k': ('Glow', 'High'),
            'z': ('Brevity', 'Off'),
            'x': ('Brevity', 'Low'),
            'c': ('Brevity', 'Medium'),
            'v': ('Brevity', 'High')
        }
        
        # Update state if it's in our mapping
        if key in key_mapping:
            fan_name, speed = key_mapping[key]
            self.fan_states[fan_name] = speed
            
        # Forward the key press to actual controller
        self.send_fan(key)

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
            activebackground="#0078D7",  # Same as bg
            activeforeground="white",    # Same as fg
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
            activebackground="#0078D7",  # Same as bg
            activeforeground="white",    # Same as fg
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
        buttons.append(('Off', lambda: self._update_fan_state('a')))
        buttons.append(('Low', lambda: self._update_fan_state('s')))
        buttons.append(('Medium', lambda: self._update_fan_state('d')))
        buttons.append(('High', lambda: self._update_fan_state('f')))
        
        # Add Glow (Fan 2) row
        buttons.append(('Glow', lambda: None))
        buttons.append(('Off', lambda: self._update_fan_state('g')))
        buttons.append(('Low', lambda: self._update_fan_state('h')))
        buttons.append(('Medium', lambda: self._update_fan_state('j')))
        buttons.append(('High', lambda: self._update_fan_state('k')))
        
        # Add Brevity (Fan 3) row
        buttons.append(('Brevity', lambda: None))
        buttons.append(('Off', lambda: self._update_fan_state('z')))
        buttons.append(('Low', lambda: self._update_fan_state('x')))
        buttons.append(('Medium', lambda: self._update_fan_state('c')))
        buttons.append(('High', lambda: self._update_fan_state('v')))
        
        # Add ALL row
        buttons.append(('ALL', lambda: None))
        buttons.append(('Off', lambda: self.all_fans_speed('Off')))
        buttons.append(('Low', lambda: self.all_fans_speed('Low')))
        buttons.append(('Medium', lambda: self.all_fans_speed('Medium')))
        buttons.append(('High', lambda: self.all_fans_speed('High')))
        
        menu = OverlayMenu(self.root, buttons, title="Fan Control")
        
        # Highlight current status after menu is created
        self._highlight_active_fan_buttons(menu)
    
    def _highlight_active_fan_buttons(self, menu):
        """Highlight buttons based on current fan states."""
        highlight_color = "#00A0FF"  # Blue highlight color
        default_color = "#444444"    # Dark gray default color
        
        # First, reset all fan buttons to default color
        for row in range(3):  # 3 fans (not including ALL row)
            for col in range(1, 5):  # 4 speeds per fan
                btn_id = f"{row}-{col}"
                if btn_id in menu.buttons:
                    menu.buttons[btn_id].config(
                        bg=default_color,
                        activebackground=default_color  # Match hover color to background
                    )
        
        # Now highlight the active buttons
        speeds = ['Off', 'Low', 'Medium', 'High']
        fans = ['Rowley', 'Glow', 'Brevity']
        
        for row, fan in enumerate(fans):
            speed = self.fan_states[fan]
            if speed in speeds:
                col = speeds.index(speed) + 1  # +1 because col 0 is the fan name
                btn_id = f"{row}-{col}"
                if btn_id in menu.buttons:
                    menu.buttons[btn_id].config(
                        bg=highlight_color,
                        activebackground=highlight_color  # Match hover color to background
                    )

    def all_fans_speed(self, speed):
        """Set all fans to the specified speed."""
        # Update all fan states first
        for fan in ['Rowley', 'Glow', 'Brevity']:
            self.fan_states[fan] = speed
        
        # Key mapping for each speed level
        if speed == 'Off':
            self._update_fan_state('a')  # Fan 1 off
            self._update_fan_state('g')  # Fan 2 off
            self._update_fan_state('z')  # Fan 3 off
        elif speed == 'Low':
            self._update_fan_state('s')  # Fan 1 low
            self._update_fan_state('h')  # Fan 2 low
            self._update_fan_state('x')  # Fan 3 low
        elif speed == 'Medium':
            self._update_fan_state('d')  # Fan 1 medium
            self._update_fan_state('j')  # Fan 2 medium
            self._update_fan_state('c')  # Fan 3 medium
        elif speed == 'High':
            self._update_fan_state('f')  # Fan 1 high
            self._update_fan_state('k')  # Fan 2 high
            self._update_fan_state('v')  # Fan 3 high

    def show_camera_menu(self):
        print("Camera button clicked")  # Debug print
        OverlayMenu(self.root, [
            ('Rowley', lambda: self.send_camera('1')),
            ('Glow', lambda: self.send_camera('2')),
            ('Brevity', lambda: self.send_camera('3')),
            ('Multi', lambda: self.send_camera('0'))
        ], title="Select Camera")
    
    def hide_main_menu(self):
        """Hide the main menu completely."""
        # Instead of just hiding buttons, make the whole window invisible
        self.root.attributes('-alpha', 0.0)  # Completely transparent
    
    def show_main_menu(self):
        """Show the main menu."""
        # Restore original transparency
        self.root.attributes('-alpha', 0.7)

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
