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
FADE_DURATION = 200  # ms
FADE_STEPS = 10
STEP_DELAY = FADE_DURATION // FADE_STEPS
TARGET_ALPHA = 0.7
HIDE_TIMEOUT = 5000  # ms
FRAME_INTERVAL = 0.03  # ~30 FPS

# Camera paths
camera_paths = {
    '1': '/dev/v4l/by-path/...-index0',
    '2': '/dev/v4l/by-path/...-index0',
    '3': '/dev/v4l/by-path/...-index0'
}

# Initialize VideoCapture objects
caps = {k: cv2.VideoCapture(p) for k, p in camera_paths.items()}
for cap in caps.values():
    cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*'MJPG'))
    cap.set(cv2.CAP_PROP_FPS, 30)

# Shared latest frames
latest_frames = {k: np.zeros((SCREEN_HEIGHT, SCREEN_WIDTH, 3), dtype=np.uint8) for k in caps}

# Capture thread
def capture_loop(key):
    cap = caps[key]
    while True:
        ret, frame = cap.read()
        if ret:
            # Resize once when storing
            latest_frames[key] = cv2.resize(frame, (SCREEN_WIDTH, SCREEN_HEIGHT))
        else:
            time.sleep(0.01)
        time.sleep(FRAME_INTERVAL)

# Start capture threads
def start_capture_threads():
    for k in caps:
        t = threading.Thread(target=capture_loop, args=(k,), daemon=True)
        t.start()

# PCA9685 setup for fan control
i2c = busio.I2C(SCL, SDA)
pca = PCA9685(i2c)
pca.frequency = 250
fan = pca.channels[0]

duty_lookup = {'a':0x0000,'s':0x3333,'d':0x6666,'f':0x9999,'g':0xCCCC,'h':0xFFFF}
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
            btn = tk.Button(self.overlay, text=text, command=lambda c=cmd: self._on_select(c),
                            width=12, height=3, relief='flat', activebackground='lightgrey')
            self.buttons.append(btn)
        self._layout_buttons()
        self._fade_in()
        self.hide_id = self.overlay.after(HIDE_TIMEOUT, self.destroy)
    def _layout_buttons(self):
        for idx, btn in enumerate(self.buttons):
            relx = (idx+1)/(len(self.buttons)+1)
            btn.place(relx=relx, rely=0.5, anchor='center')
    def _fade_in(self, step=0):
        if not self.overlay.winfo_exists(): return
        alpha = TARGET_ALPHA * (step/FADE_STEPS)
        self.overlay.attributes('-alpha', alpha)
        if step<FADE_STEPS:
            self.overlay.after(STEP_DELAY, lambda: self._fade_in(step+1))
    def _fade_out(self, step=FADE_STEPS):
        if not self.overlay.winfo_exists(): return
        alpha = TARGET_ALPHA * (step/FADE_STEPS)
        self.overlay.attributes('-alpha', alpha)
        if step>0:
            self.overlay.after(STEP_DELAY, lambda: self._fade_out(step-1))
        else:
            self.destroy()
    def _on_select(self, cmd):
        self.overlay.after_cancel(self.hide_id)
        cmd()
        self._fade_out()
    def destroy(self):
        if self.overlay.winfo_exists(): self.overlay.destroy()

class UIApp:
    def __init__(self):
        start_capture_threads()
        self.root = tk.Tk()
        self.root.attributes('-fullscreen', True)
        self.root.configure(bg='black')
        self.current_menu = None
        self.current_mode = 'multi'
        self.multiview_selection = ['1','2']
        # video label
        self.video_label = tk.Label(self.root, bg='black')
        self.video_label.pack(fill='both', expand=True)
        # bindings
        self.root.bind('<Button-1>', self.show_main_menu)
        # begin loop
        self.root.after(0, self.update_frame)
        # keystroke listener
        self.listener = Listener(on_press=self.on_press, on_release=self.on_release)
        self.listener.start()
    def update_frame(self):
        # fetch composite frame
        if self.current_mode in ['1','2','3']:
            frame = latest_frames[self.current_mode]
        elif self.current_mode=='multi' and len(self.multiview_selection)==2:
            f1 = latest_frames[self.multiview_selection[0]]
            f2 = latest_frames[self.multiview_selection[1]]
            h,w,_ = f1.shape
            left = cv2.resize(f1,(w//2,h))
            right= cv2.resize(f2,(w//2,h))
            frame = np.hstack((left,right))
        else:
            frame = np.zeros((SCREEN_HEIGHT,SCREEN_WIDTH,3),dtype=np.uint8)
        # convert & display
        img = cv2.cvtColor(frame,cv2.COLOR_BGR2RGB)
        im = Image.fromarray(img)
        self.photo = ImageTk.PhotoImage(im)
        self.video_label.config(image=self.photo)
        self.root.after(int(FRAME_INTERVAL*1000), self.update_frame)
    def show_main_menu(self,event=None):
        self._destroy_menu()
        self.current_menu=OverlayMenu(self.root,[('Cameras',self.show_camera_menu),('Fans',self.show_fan_menu)])
    def show_camera_menu(self):
        self._destroy_menu()
        self.current_menu=OverlayMenu(self.root,[( '1',lambda:self.send_key('1')),( '2',lambda:self.send_key('2')),( '3',lambda:self.send_key('3')),( 'Multi',lambda:self.send_key('0'))])
    def show_fan_menu(self):
        self._destroy_menu()
        keys=['a','s','d','f','g','h'];labels=['0%','20%','40%','60%','80%','100%']
        self.current_menu=OverlayMenu(self.root,[(lbl,lambda k=k:self.send_key(k)) for lbl,k in zip(labels,keys)])
    def send_key(self,k):
        keyboard_ctrl.press(k);keyboard_ctrl.release(k);self.on_key(k)
    def on_key(self,c):
        if c in duty_lookup: fan.duty_cycle=duty_lookup[c]
        elif c in ['1','2','3']: self.current_mode=c;self.multiview_selection=[]
        elif c=='0': self.current_mode='multi';self.multiview_selection=[]
        elif self.current_mode=='multi' and c in ['1','2','3'] and len(self.multiview_selection)<2:
            self.multiview_selection.append(c)
    def on_press(self,key):
        if hasattr(key,'char') and key.char: self.on_key(key.char.lower())
    def on_release(self,key):
        if key==Key.esc: self.cleanup(); return False
    def _destroy_menu(self):
        if self.current_menu: self.current_menu.destroy(); self.current_menu=None
    def cleanup(self):
        fan.duty_cycle=0x0000; pca.deinit(); self.listener.stop(); self.root.destroy()
    def run(self): self.root.mainloop()

if __name__=='__main__': UIApp().run()
```
