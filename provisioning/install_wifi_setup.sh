#!/bin/bash
# Install WiFi setup services (captive portal + USB config + network watchdog)
set -e

echo "==> Installing WiFi setup services..."

# Copy files
sudo cp provisioning/wifi_portal.py /home/sjc/dreammachine/provisioning/
sudo cp provisioning/usb_wifi_config.sh /home/sjc/dreammachine/provisioning/
sudo cp provisioning/network_watchdog.sh /home/sjc/dreammachine/provisioning/
sudo cp provisioning/show_watchdog.sh /home/sjc/dreammachine/provisioning/
sudo cp provisioning/wifi-portal.service /etc/systemd/system/
sudo cp provisioning/usb-wifi-config.service /etc/systemd/system/
sudo cp provisioning/network-watchdog.service /etc/systemd/system/
sudo cp provisioning/show-watchdog.service /etc/systemd/system/

# Set permissions
sudo chmod +x /home/sjc/dreammachine/provisioning/usb_wifi_config.sh
sudo chmod +x /home/sjc/dreammachine/provisioning/network_watchdog.sh
sudo chmod +x /home/sjc/dreammachine/provisioning/show_watchdog.sh
sudo chown -R sjc:sjc /home/sjc/dreammachine/provisioning/

# Enable services
sudo systemctl daemon-reload
sudo systemctl enable wifi-portal.service
sudo systemctl enable usb-wifi-config.service
sudo systemctl enable network-watchdog.service
sudo systemctl enable show-watchdog.service
sudo systemctl restart wifi-portal.service
sudo systemctl restart usb-wifi-config.service
sudo systemctl restart network-watchdog.service
sudo systemctl restart show-watchdog.service

echo "==> WiFi setup services installed"
echo "    - Captive portal: monitors WiFi continuously, opens hotspot after"
echo "      ~1 min of no connectivity (first boot, relocation, or mid-session drop)"
echo "    - USB config: watches forever for dreammachine-wifi.txt on USB drives"
echo "    - Network watchdog: restarts NetworkManager after ~2 min down,"
echo "      reboots only if network is ALSO down AND the show (REAPER+LED)"
echo "      is not healthy — never reboots a working show for network reasons"
echo "    - Show watchdog: restarts lightdm after ~3 min of REAPER not running"
echo "      (recovers a hung X session), reboots only as a last resort if"
echo "      that doesn't bring REAPER back"
