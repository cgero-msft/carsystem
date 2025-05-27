#PACKAGES REQUIRED

sudo apt install python3-pip
pip3 install opencv-python
pip3 install tkinter #this one throws an error for some reason: ERROR: Could not find a version that satisfies the requirement tkinter
, ERROR: No matching distribution found for tkinter
pip3 install adafruit-circuitpython-pca9685
pip3 install pynput



sudo apt-get install libcblas-dev #this makes it work


#force no cursor
sudo nano /etc/lightdm/lightdm.conf
#add below the [Seat*] section:
xserver-command = X -nocursor

