#!/bin/bash
# Install DREAMMACHINE show-hours gating (09:45 open / 23:00 close) and the
# nightly maintenance reboot (03:00, inside the closed window).
#
# IMPORTANT: these use OnCalendar in the Pi's LOCAL system timezone. Verify
# with `timedatectl` that the unit's timezone matches the venue's before
# relying on this — if it's wrong, set it with:
#   sudo timedatectl set-timezone America/Mexico_City
set -e

echo "==> Installing show-hours gating + nightly maintenance reboot..."

sudo cp provisioning/show_hours_gate.sh /home/sjc/dreammachine/provisioning/
sudo chmod +x /home/sjc/dreammachine/provisioning/show_hours_gate.sh
sudo chown sjc:sjc /home/sjc/dreammachine/provisioning/show_hours_gate.sh

sudo cp provisioning/dreammachine-show-open.service /etc/systemd/system/
sudo cp provisioning/dreammachine-show-open.timer /etc/systemd/system/
sudo cp provisioning/dreammachine-show-close.service /etc/systemd/system/
sudo cp provisioning/dreammachine-show-close.timer /etc/systemd/system/
sudo cp provisioning/dreammachine-nightly-reboot.service /etc/systemd/system/
sudo cp provisioning/dreammachine-nightly-reboot.timer /etc/systemd/system/

sudo systemctl daemon-reload
sudo systemctl enable --now dreammachine-show-open.timer
sudo systemctl enable --now dreammachine-show-close.timer
sudo systemctl enable --now dreammachine-nightly-reboot.timer

echo "==> Installed. Current timezone:"
timedatectl | grep "Time zone"
echo "==> Timers:"
systemctl list-timers 'dreammachine-*' --no-pager
