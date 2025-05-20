```python
import tkinter as tk
from PIL import Image, ImageTk
import cv2
import numpy as np
import threading
import time
from pynput.keyboard import Controller, Key, Listener
from board import SCL, SDA
import busio
from adafruit_pca9685 import PCA9685

# Constants
SCREEN_WIDTH = 1024
SCREEN_HEIGHT = 600
FADE_DURATION = 200
FADE_STEPS = 10
STEP_DELAY = FADE_DURATION // FADE_STEPS
TARGET_ALPHA = 0.7
HIDE_TIMEOUT = 5000

# Camera paths
camera_paths = {
    '1': '/dev/v4l/by-path/platform-fd500000.pcie-pci-0000:01:00.0-usb-0:1.1.4:1.0-video-index0',
    '2': '/dev/v4l/by-path/platform-fd500000.pcie-pci-0000:01:00.0-usb-0:1.1.3:1.0-video-index0',
    '3': '/dev/v4l/by-path/platform-fd500000.pcie-pci-0000:01:00.0-usb-0:1.1.2:1.0-video-index0'
}

def get_frame(path):
    cap = cv2.VideoCapture(path)
    if not cap.isOpened():
        return np.zeros((SCREEN_HEIGHT, SCREEN_WIDTH, 3), dtype=np.uint8)
    ret, frame = cap.read()
    cap.release()
    if not ret:
        return np.zeros((SCREEN_HEIGHT, SCREEN_WIDTH, 3), dtype=np.uint8)
    return cv2.resize(frame, (SCREEN_WIDTH, SCREEN_HEIGHT))

# PDA9685 setup for fan control
i2c = busio.I2C(SCL, SDA)
pca = PCA9685(i2c)
pca.frequency = 250
fan = pca.channels[0]

duty_lookup = {
    'a': 0x0000,
    's': 0x3333,
    'd': 0x6666,
    'f': 0x9999,
    'g': 0xCCCC,
    'h': 0xFFFF
}

# Keyboard controller
keyboard_ctrl = Controller()

class OverlayMenu:
    def __init__(self, root, buttons):
        self.root = root
        self.overlay = tk.Toplevel(root)
        self.overlay.attributes('-fullscreen', True)
        self.overlay.attributes('-alpha', 0.0)
        self.overlay.configure(bg='white')
        self.buttons = []
        for text, cmd in buttons:
            btn = tk.Button(
                self.overlay,
                text=text,
                command=lambda c=cmd: self._on_select(c),
                width=10,
                height=2,
                relief='flat',
                activebackground='lightgrey'
            )
            self.buttons.append(btn)
        self._layout_buttons()
        self._fade_in()
        self.hide_id = self.overlay.after(HIDE_TIMEOUT, self.destroy)

    def _layout_buttons(self):
        count = len(self.buttons)
        for idx, btn in enumerate(self.buttons):
            relx = (idx + 1) / (count + 1)
            btn.place(relx=relx, rely=0.5, anchor='center')

    def _fade_in(self, step=0):
        alpha = (TARGET_ALPHA / FADE_STEPS) * step
        self.overlay.attributes('-alpha', alpha)
        if step < FADE_STEPS:
            self.overlay.after(STEP_DELAY, lambda: self._fade_in(step+1))

    def _fade_out(self, step=FADE_STEPS):
        alpha = (TARGET_ALPHA / FADE_STEPS) * step
        self.overlay.attributes('-alpha', alpha)
        if step > 0:
            self.overlay.after(STEP_DELAY, lambda: self._fade_out(step-1))
        else:
            self.destroy()

    def _on_select(self, cmd):
        self.overlay.after_cancel(self.hide_id)
        cmd()
        self._fade_out()

    def destroy(self):
        if self.overlay.winfo_exists():
            self.overlay.destroy()

class UIApp:
    def __init__(self):
        self.root = tk.Tk()
        self.root.attributes('-fullscreen', True)
        self.root.configure(bg='black')
        self.current_menu = None
        self.current_mode = None
        self.multiview_selection = []
        # Video display label
        self.video_label = tk.Label(self.root)
        self.video_label.place(relx=0.5, rely=0.5, anchor='center')
        # Bind screen tap
        self.root.bind('<Button-1>', self.show_main_menu)
        # Start camera update loop
        self.root.after(0, self.update_frame)
        # Start hotkey listener
        self.listener = Listener(on_press=self.on_press, on_release=self.on_release)
        self.listener.start()

    def update_frame(self):
        # Choose mode
        if self.current_mode in ['1','2','3']:
            frame = get_frame(camera_paths[self.current_mode])
        elif len(self.multiview_selection) == 0 and self.current_mode == 'multi':
            # do nothing until two selected
            frame = np.zeros((SCREEN_HEIGHT, SCREEN_WIDTH, 3), dtype=np.uint8)
        elif self.current_mode == 'multi' and self.multiview_selection:
            # show first selected only until second arrives
            frame = get_frame(camera_paths[self.multiview_selection[0]])
        else:
            frame = np.zeros((SCREEN_HEIGHT, SCREEN_WIDTH, 3), dtype=np.uint8)
        # Convert to PhotoImage
        img = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        img = Image.fromarray(img)
        img = img.resize((SCREEN_WIDTH, SCREEN_HEIGHT))
        self.photo = ImageTk.PhotoImage(img)
        self.video_label.configure(image=self.photo)
        self.root.after(30, self.update_frame)

    def show_main_menu(self, event=None):
        self._destroy_menu()
        buttons = [
            ('Cameras', self.show_camera_menu),
            ('Fans', self.show_fan_menu)
        ]
        self.current_menu = OverlayMenu(self.root, buttons)

    def show_camera_menu(self):
        self._destroy_menu()
        buttons = [
            ('Camera 1', lambda: self.send_key('1')),
            ('Camera 2', lambda: self.send_key('2')),
            ('Camera 3', lambda: self.send_key('3')),
            ('Multi',    lambda: self.send_key('0'))
        ]
        self.current_menu = OverlayMenu(self.root, buttons)

    def show_fan_menu(self):
        self._destroy_menu()
        fan_keys = ['a', 's', 'd', 'f', 'g', 'h']
        fan_labels = ['0%', '20%', '40%', '60%', '80%', '100%']
        buttons = [(label, lambda k=key: self.send_key(k)) for label, key in zip(fan_labels, fan_keys)]
        self.current_menu = OverlayMenu(self.root, buttons)

    def send_key(self, key_char):
        # emit
        keyboard_ctrl.press(key_char)
        keyboard_ctrl.release(key_char)
        # handle
        self.on_key(key_char)

    def on_key(self, c):
        # fan control
        if c in duty_lookup:
            fan.duty_cycle = duty_lookup[c]
        # camera modes
        elif c in ['1','2','3']:
            if self.current_mode != 'multi':
                self.current_mode = c
                self.multiview_selection = []
        elif c == '0':
            self.current_mode = 'multi'
            self.multiview_selection = []
        elif self.current_mode == 'multi' and c in ['1','2','3']:
            if c not in self.multiview_selection:
                self.multiview_selection.append(c)
            if len(self.multiview_selection)==2:
                # switch to multiview: not fully implemented; UI just shows single first
                pass

    def on_press(self, key):
        try:
            if hasattr(key, 'char') and key.char:
                self.on_key(key.char.lower())
        except:
            pass

    def on_release(self, key):
        if key == Key.esc:
            self.cleanup()
            return False

    def _destroy_menu(self):
        if self.current_menu:
            self.current_menu.destroy()
            self.current_menu = None

    def cleanup(self):
        fan.duty_cycle = 0x0000
        pca.deinit()
        self.listener.stop()
        self.root.destroy()

    def run(self):
        # start default view
        self.current_mode = 'multi'
        self.multiview_selection = ['1','2']
        self.root.mainloop()

if __name__ == '__main__':
    app = UIApp()
    app.run()
```
