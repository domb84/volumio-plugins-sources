#!/bin/bash

# If you need to differentiate install for armhf and i386 you can get the variable like this
#DPKG_ARCH=`dpkg --print-architecture`
# Then use it to differentiate your install
echo "Installing teac-dab-controls Dependencies"
apt-get update
# Install the required packages via apt-get
apt-get -y install pigpio python3-dev

pip3 install python-engineio==3.14.2 python-socketio[client]==4.6.0 adafruit-blinka Adafruit-PlatformDetect adafruit-python-shell adafruit_circuitpython_mcp3xxx adafruit_circuitpython_bitbangio RPi.GPIO pigpio retrying fastapi uvicorn spidev
pip3 install git+https://github.com/domb84/rpi-lcd-menu.git

# use pwm mode for pigpiod
sed -i "/ExecStart=/c\ExecStart=/usr/bin/pigpiod -t 0" /lib/systemd/system/pigpiod.service

# fix issue with 3.569 breaking gpio permisions
# https://community.volumio.com/t/update-to-volumio-3-569-breaks-gpio-permission/64095
sed -i "s/bcm2835-gpiomem/gpiomem/g" /etc/udev/rules.d/99-com.rules

# # add ir pins to userconfig
# config_file="/boot/userconfig.txt"
# pattern="dtoverlay=gpio-ir"

# # Remove lines containing the specified pattern
# sudo sed -i "/$pattern/d" "$config_file"
# # Add new lines to the end of the file
# echo "dtoverlay=gpio-ir,gpio_pin=25" | sudo tee -a "$config_file" > /dev/null
# echo "dtoverlay=gpio-ir,gpio_pin=6" | sudo tee -a "$config_file" > /dev/null

cp /data/plugins/user_interface/teac-dab-controls/teac-dab-controls.service /lib/systemd/system/

systemctl daemon-reload -q

#requred to end the plugin install
echo "plugininstallend"