import tkinter as tk
import threading
from pynput.keyboard import Controller
# Import your existing main() function that starts the cv2 windows & listener
from UnifiedTestStableFullscreen import main

class OverlayMenu:
    def __init__(self, root, buttons):
        self.overlay = tk.Toplevel(root)
        self.overlay.attributes('-fullscreen', True, '-alpha', 0.7, '-topmost', True)
        self.overlay.configure(bg='white')
        for idx, (text, cmd) in enumerate(buttons):
            btn = tk.Button(self.overlay, text=text,
                            command=lambda c=cmd: self._select(c), width=12, height=3)
            btn.place(relx=(idx+1)/(len(buttons)+1), rely=0.5, anchor='center')
        self.overlay.after(5000, self.destroy)

    def _select(self, cmd):
        cmd()
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
        # Create an invisible fullscreen window that still captures clicks
        root.overrideredirect(True)
        root.attributes('-fullscreen', True, '-topmost', True)
        # Fully transparent window
        root.attributes('-alpha', 0.0)
        # Ensure it covers the entire screen
        root.geometry(f"{root.winfo_screenwidth()}x{root.winfo_screenheight()}+0+0")

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
            OverlayMenu(root, [(lbl, lambda k=k: self.send_fan(k)) for lbl,k in zip(labels,keys)])

        root.bind('<Button-1>', show_main)
        root.mainloop()

if __name__ == '__main__':
    # Start background camera/fan process
    cam_thread = threading.Thread(target=main, daemon=True)
    cam_thread.start()

    # Start overlay
    ui = UIOverlay(
        send_camera=lambda c: Controller().press(c) or Controller().release(c),
        send_fan=lambda k: Controller().press(k) or Controller().release(k)
    )
    ui.start()
    cam_thread.join()