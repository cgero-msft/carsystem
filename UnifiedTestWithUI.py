import cv2
import numpy as np
import threading
import time
import tkinter as tk
from pynput import keyboard
from board import SCL, SDA
import busio
from adafruit_pca9685 import PCA9685

# --- OverlayMenu and helper to bind clicks ---
def install_opencv_callback(window_name, popup_fn):
    def on_mouse(event, x, y, flags, param):
        if event == cv2.EVENT_LBUTTONDOWN:
            popup_fn()
    cv2.setMouseCallback(window_name, on_mouse)

class OverlayMenu:
    def __init__(self, root, buttons):
        self.overlay = tk.Toplevel(root)
        self.overlay.attributes('-fullscreen', True, '-alpha', 0.7, '-topmost', True)
        self.overlay.configure(bg='white')
        for idx, (text, cmd) in enumerate(buttons):
            btn = tk.Button(self.overlay, text=text, command=lambda c=cmd: self._select(c),
                            width=12, height=3)
            btn.place(relx=(idx+1)/(len(buttons)+1), rely=0.5, anchor='center')
        self.overlay.after(5000, self.destroy)

    def _select(self, cmd):
        cmd()
        self.destroy()

    def destroy(self):
        if self.overlay.winfo_exists():
            self.overlay.destroy()

# --- Camera & Fan setup ---
camera_paths = {
    '1': '/dev/v4l/by-path/platform-fd500000.pcie-pci-0000:01:00.0-usb-0:1.1.4:1.0-video-index0',
    '2': '/dev/v4l/by-path/platform-fd500000.pcie-pci-0000:01:00.0-usb-0:1.1.3:1.0-video-index0',
    '3': '/dev/v4l/by-path/platform-fd500000.pcie-pci-0000:01:00.0-usb-0:1.1.2:1.0-video-index0'
}
current_mode = None
stop_thread = False
display_thread = None
multiview_selection = []
SCREEN_WIDTH, SCREEN_HEIGHT = 1024, 600

def get_single_frame(path):
    cap = cv2.VideoCapture(path)
    if not cap.isOpened(): return np.zeros((SCREEN_HEIGHT, SCREEN_WIDTH, 3), np.uint8)
    ret, frame = cap.read(); cap.release()
    if not ret: return np.zeros((SCREEN_HEIGHT, SCREEN_WIDTH, 3), np.uint8)
    return cv2.resize(frame, (SCREEN_WIDTH, SCREEN_HEIGHT))

duty_lookup = {'a':0x0000,'s':0x3333,'d':0x6666,'f':0x9999,'g':0xCCCC,'h':0xFFFF}

# --- Hotkey callbacks ---
def on_press(key):
    global multiview_selection, current_mode
    try:
        if hasattr(key, 'char') and key.char:
            c = key.char.lower()
            if c in duty_lookup:
                fan.duty_cycle = duty_lookup[c]
            elif c in ['1','2','3'] and current_mode != 'multi_select':
                switch_mode(c)
            elif c == '0':
                current_mode = 'multi_select'; multiview_selection = []
            elif current_mode == 'multi_select' and c in ['1','2','3']:
                if c not in multiview_selection:
                    multiview_selection.append(c)
                if len(multiview_selection) == 2:
                    switch_mode('multi', multiview_selection)
                    multiview_selection = []
    except: pass

def on_release(key):
    if key == keyboard.Key.esc:
        cleanup()
        return False

# --- Display threads ---
def show_multiview(cam_keys):
    global stop_thread
    stop_thread = False
    def display():
        caps = [cv2.VideoCapture(camera_paths[k], cv2.CAP_V4L2) for k in cam_keys]
        for cap in caps:
            cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*'MJPG'))
            cap.set(cv2.CAP_PROP_FPS, 30)
        window_name = 'Camera View'
        cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)
        time.sleep(0.5)
        cv2.moveWindow(window_name,0,0); cv2.resizeWindow(window_name,SCREEN_WIDTH,SCREEN_HEIGHT)
        cv2.setWindowProperty(window_name, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)
        while not stop_thread:
            frames = []
            for cap in caps:
                ret, frame = cap.read()
                if not ret: frame = np.zeros((SCREEN_HEIGHT, SCREEN_WIDTH//2,3), np.uint8)
                frames.append(cv2.resize(frame,(SCREEN_WIDTH//2,SCREEN_HEIGHT)))
            background = np.hstack(frames)
            cv2.imshow(window_name, background)
            cv2.waitKey(1)
        for cap in caps: cap.release()
    th = threading.Thread(target=display, daemon=True); th.start(); return th

def show_single(cam_key):
    global stop_thread
    stop_thread = False
    def display():
        cap = cv2.VideoCapture(camera_paths[cam_key])
        window_name='Camera View'
        cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)
        cv2.setWindowProperty(window_name, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)
        while not stop_thread:
            ret, frame = cap.read()
            if not ret: continue
            h,w=frame.shape[:2]
            scale=min(SCREEN_WIDTH/w,SCREEN_HEIGHT/h)
            nw,nh=int(w*scale),int(h*scale)
            frame=cv2.resize(frame,(nw,nh))
            bg=np.zeros((SCREEN_HEIGHT,SCREEN_WIDTH,3),np.uint8)
            x=(SCREEN_WIDTH-nw)//2; y=(SCREEN_HEIGHT-nh)//2
            bg[y:y+nh,x:x+nw]=frame
            cv2.imshow(window_name,bg); cv2.waitKey(1)
        cap.release()
    th=threading.Thread(target=display, daemon=True); th.start(); return th

def switch_mode(mode, cam_keys=None):
    global current_mode, stop_thread, display_thread
    stop_thread = True
    if display_thread and display_thread.is_alive(): display_thread.join()
    current_mode = mode
    if mode == 'multi': display_thread = show_multiview(cam_keys)
    else: display_thread = show_single(mode)

# --- Fan setup ---
i2c = busio.I2C(SCL, SDA)
pca = PCA9685(i2c)
pca.frequency = 250
fan = pca.channels[0]

# --- Cleanup ---
def cleanup():
    global stop_thread
    stop_thread = True
    cv2.destroyAllWindows()
    pca.deinit()

# --- Main entry with overlay integration ---
def main():
    print("🎥 Webcam viewer ready")
    print("🕹️ Hotkeys: 1/2/3, 0+2 cams, A/S/D/F/G/H, ESC to exit")
    # Prepare hidden Tk root for overlays
    root = tk.Tk(); root.withdraw()
    # Setup cv2 window
    window_name='Camera View'
    switch_mode('multi',['1','2'])
    install_opencv_callback(window_name,
        lambda: OverlayMenu(root,[
            ('Cameras', lambda: OverlayMenu(root,[('1',lambda:press('1')),('2',lambda:press('2')),('3',lambda:press('3')),('Multi',lambda:press('0'))])),
            ('Fans',    lambda: OverlayMenu(root,list(zip(['0%','20%','40%','60%','80%','100%'], [lambda k=k:press(k) for k in ['a','s','d','f','g','h']]))))
        ])
    )
    # Start listener and keep main thread alive
    with keyboard.Listener(on_press=on_press, on_release=on_release):
        keyboard.Listener.join

if __name__ == '__main__':
    main()