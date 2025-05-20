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
        
        # Get screen dimensions to ensure we cover the entire display
        screen_width = root.winfo_screenwidth()
        screen_height = root.winfo_screenheight()
        root.geometry(f"{screen_width}x{screen_height}+0+0")
        
        # Set to fullscreen and remove window decorations
        root.attributes('-fullscreen', True)
        root.overrideredirect(True)
        
        # Make it nearly invisible (0.01 is practically invisible but still captures clicks)
        root.attributes('-alpha', 0.01)  # Almost completely transparent
        
        # Black background (which will be nearly invisible with alpha=0.01)
        root.configure(bg='black')
        
        # Add optional visual indicator for clicks (helpful for debugging)
        click_indicator = tk.Label(root, text="", bg="black")
        click_indicator.place(x=0, y=0)
        
        def show_click(e):
            # Optional: briefly show where the click happened for debugging
            click_indicator.config(text="●", fg="red")
            click_indicator.place(x=e.x, y=e.y)
            root.after(200, lambda: click_indicator.config(text=""))
            # Show the main menu
            show_main(e)
        
        # Rest of your code remains the same
        def show_main(e=None):
            OverlayMenu(root, [
                ('Cameras', show_camera),
                ('Fans',    show_fans)
            ])
            
        # Other functions remain the same...
        
        # Bind click event to our enhanced handler to show feedback
        root.bind('<Button-1>', show_click)
        
        # Make sure the window stays on top
        root.attributes('-topmost', True)
        
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