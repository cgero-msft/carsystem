import time
from board import SCL, SDA
import busio
from adafruit_pca9685 import PCA9685
from pynput import keyboard

# Set up I2C and PCA9685
i2c = busio.I2C(SCL, SDA)
pca = PCA9685(i2c)
pca.frequency = 250  # 250 Hz is good for fans

# Fan on channel 0
fan = pca.channels[0]

# Fan speed lookup table
duty_lookup = {
    'z': 0x0000,     # 0%
    'x': 0x3333,     # 20%
    'c': 0x6666,     # 40%
    'v': 0x9999,     # 60%
    'b': 0xCCCC,     # 80%
    'n': 0xFFFF,     # 100%
}

def on_press(key):
    try:
        k = key.char.lower()
        if k in duty_lookup:
            duty = duty_lookup[k]
            fan.duty_cycle = duty
            percent = int((duty / 0xFFFF) * 100)
            print(f"[KEY '{k.upper()}'] → Fan speed set to {percent}%")
    except AttributeError:
        pass  # Ignore special keys

def on_release(key):
    if key == keyboard.Key.esc:
        print("Exiting...")
        fan.duty_cycle = 0x0000
        pca.deinit()
        return False

print("Press Z/X/C/V/B/N to control fan speed (ESC to quit)...")

# Start keyboard listener
with keyboard.Listener(on_press=on_press, on_release=on_release) as listener:
    listener.join()
