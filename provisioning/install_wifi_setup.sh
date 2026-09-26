#!/bin/bash
# Install WiFi setup services (captive portal + USB config)
set -e

echo "==> Installing WiFi setup services..."

# Copy files
sudo cp provisioning/wifi_portal.py /home/sjc/dreammachine/provisioning/
sudo cp provisioning/usb_wifi_config.sh /home/sjc/dreammachine/provisioning/
sudo cp provisioning/wifi-portal.service /etc/systemd/system/
sudo cp provisioning/usb-wifi-config.service /etc/systemd/system/

# Set permissions
sudo chmod +x /home/sjc/dreammachine/provisioning/usb_wifi_config.sh
sudo chown -R sjc:sjc /home/sjc/dreammachine/provisioning/

# Enable services
sudo systemctl daemon-reload
sudo systemctl enable wifi-portal.service
sudo systemctl enable usb-wifi-config.service

echo "==> WiFi setup services installed"
echo "    - Captive portal: starts if no WiFi configured"
echo "    - USB config: watches for dreammachine-wifi.txt on USB drives"
