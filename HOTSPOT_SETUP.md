# Dogmobile Hotspot Setup

## Table of Contents

1. [Enabling NetworkManager on Raspberry Pi OS Bullseye](#1-enabling-networkmanager-on-raspberry-pi-os-bullseye)
   - [Prerequisites](#prerequisites)
   - [Installation Steps](#installation-steps)
   - [Reverting to Original Settings (dhcpcd)](#reverting-to-original-settings-dhcpcd)
2. [Connecting to Dogmobile from an iPhone](#2-connecting-to-dogmobile-from-an-iphone)
   - [Connecting to the Hotspot](#connecting-to-the-hotspot)
   - [Opening the Remote Control UI](#opening-the-remote-control-ui)
   - [Installing as a PWA (Home Screen App)](#installing-as-a-pwa-home-screen-app)
   - [Disconnecting](#disconnecting)

---

## 1. Enabling NetworkManager on Raspberry Pi OS Bullseye

### Prerequisites

> **Note:** This guide is for **Raspberry Pi OS Bullseye (VERSION_ID=11)**. Bookworm (Debian 12) already uses NetworkManager by default.

> ⚠️ **Warning:** Before making changes, ensure you have **physical access to the Pi** (keyboard + display) or an **Ethernet cable connected**. Switching from `dhcpcd` to NetworkManager can cause your Wi-Fi connection to drop temporarily. Having an alternative way to access the Pi will let you reconfigure networking if needed.

### Installation Steps

1. **Update and install NetworkManager:**

   ```bash
   sudo apt update
   sudo apt install network-manager
   ```

2. **Stop and disable dhcpcd:**

   ```bash
   sudo systemctl stop dhcpcd
   sudo systemctl disable dhcpcd
   ```

3. **Enable and start NetworkManager:**

   ```bash
   sudo systemctl enable NetworkManager
   sudo systemctl start NetworkManager
   ```

4. **Verify NetworkManager is running:**

   ```bash
   sudo systemctl status NetworkManager
   nmcli device status
   ```

   You should see `wlan0` appear in the device list. Its state will typically show as `connected` (if already on Wi-Fi) or `disconnected`.

5. **Ensure `/etc/network/interfaces` only has the loopback entry:**

   ```
   auto lo
   iface lo inet loopback
   ```

   If the file contains entries for `wlan0` or `eth0`, remove them so NetworkManager can fully manage those interfaces. NetworkManager will ignore interfaces declared in `/etc/network/interfaces`.

6. **Allow passwordless `nmcli` for the carsystem user** by creating `/etc/sudoers.d/carsystem`:

   ```bash
   sudo visudo -f /etc/sudoers.d/carsystem
   ```

   Add the following line:

   ```
   cgero88 ALL=(ALL) NOPASSWD: /usr/bin/nmcli
   ```

7. **Reconnect to home Wi-Fi** if your connection dropped during the switch:

   ```bash
   sudo nmcli device wifi connect "YourSSID" password "YourPassword"
   ```

8. **Reboot:**

   ```bash
   sudo reboot
   ```

9. **Test the hotspot manually** after rebooting:

   ```bash
   sudo nmcli device wifi hotspot ifname wlan0 ssid Dogmobile password RowGlowBrev
   ```

   You should see **"Dogmobile"** appear in your phone's Wi-Fi list. Once confirmed, stop and clean up the test hotspot:

   ```bash
   sudo nmcli connection down DogmobileHotspot && sudo nmcli connection delete DogmobileHotspot
   ```

---

### Reverting to Original Settings (dhcpcd)

If you need to undo the changes and return to the default Bullseye networking stack:

1. **Stop and disable NetworkManager:**

   ```bash
   sudo systemctl stop NetworkManager
   sudo systemctl disable NetworkManager
   ```

2. **Re-enable and start dhcpcd:**

   ```bash
   sudo systemctl enable dhcpcd
   sudo systemctl start dhcpcd
   ```

3. **(Optional) Remove NetworkManager:**

   ```bash
   sudo apt remove network-manager
   ```

4. **Remove the sudoers file:**

   ```bash
   sudo rm /etc/sudoers.d/carsystem
   ```

5. **Restore `/etc/network/interfaces`** if you removed any entries. The default Bullseye content is:

   ```
   # interfaces(5) file used by ifup(8) and ifdown(8)
   # Include files from /etc/network/interfaces.d:
   source /etc/network/interfaces.d/*
   ```

6. **Reboot:**

   ```bash
   sudo reboot
   ```

> **Note:** Your existing Wi-Fi credentials stored in `/etc/wpa_supplicant/wpa_supplicant.conf` are preserved and will be picked up automatically by dhcpcd after the reboot — no need to re-enter your Wi-Fi password.

---

## 2. Connecting to Dogmobile from an iPhone

### Connecting to the Hotspot

1. On the Pi's touchscreen, tap the **📡 Hotspot** button — it turns green and shows **📡 ON**.
2. On your iPhone, go to **Settings → Wi-Fi**.
3. Look for the network **"Dogmobile"** and tap it.
4. Enter the password: **RowGlowBrev**
5. You should see a checkmark next to Dogmobile.

> **Note:** iOS will show **"No Internet Connection"** next to Dogmobile — this is expected. The Pi hotspot provides local access only and does not route internet traffic.

6. If iOS shows a **"This network has no internet"** prompt, tap **"Use Without Internet"** or **"Join Anyway"**.

---

### Opening the Remote Control UI

1. Open **Safari** (Safari is required for PWA installation to work).
2. Navigate to: **http://10.42.0.1:8080**
3. You should see the Dogmobile remote control interface with camera and fan controls.

---

### Installing as a PWA (Home Screen App)

1. In Safari, tap the **Share** button (the square with an arrow pointing up).
2. Scroll down and tap **"Add to Home Screen"**.
3. Name it **"Dogmobile"** (or whatever you prefer) and tap **Add**.
4. The app icon will appear on your home screen.
5. When you open it from the home screen, it launches fullscreen without any browser chrome — it looks and feels like a native app.

> **Note:** The PWA only works when your iPhone is connected to the **Dogmobile** Wi-Fi network.

---

### Disconnecting

1. On the Pi's touchscreen, tap the **📡 ON** button to turn off the hotspot.
2. The button returns to gray **📡 Hotspot**.
3. Your iPhone will automatically disconnect from Dogmobile and should reconnect to your regular Wi-Fi.
