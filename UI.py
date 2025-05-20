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
        root.attributes('-fullscreen', True)
        root.attributes('-transparentcolor', 'black')  # make background click-through if supported
        root.configure(bg='black')
        root.overrideredirect(True)

        def show_main(e=None):
            OverlayMenu(root, [
                ('Cameras', show_camera),
                ('Fans',    show_fans)
            ])

        def show_camera():
            OverlayMenu(root, [
                ('1', lambda: self.send_camera('1')),
                ('2', lambda: self.send_camera('2')),
                ('3', lambda: self.send_camera('3')),
                ('Multi', lambda: self.send_camera('0'))
            ])

        def show_fans():
            keys = ['a','s','d','f','g','h']
            labels = ['0%','20%','40%','60%','80%','100%']
            OverlayMenu(root, [
                (lbl, lambda k=k: self.send_fan(k)) for lbl,k in zip(labels,keys)
            ])

        root.bind('<Button-1>', show_main)
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