#!/bin/bash
# Install DREAMMACHINE fleet monitoring: boot notification, on-demand
# Telegram status bot (/status, /update, /flash, ...), and a periodic
# heartbeat during show hours. Originally a dm4-only prototype
# (golden-master/sjcdm4/dm-state/); this is the tracked, fleet-deployable
# version.
set -e

echo "==> Installing DREAMMACHINE monitoring (Telegram + email)..."

sudo cp provisioning/monitoring/notify.py /home/sjc/notify.py
sudo cp provisioning/monitoring/notify_boot.sh /home/sjc/notify_boot.sh
sudo cp provisioning/monitoring/telegram_bot.py /home/sjc/telegram_bot.py
sudo chmod +x /home/sjc/notify_boot.sh
sudo chown sjc:sjc /home/sjc/notify.py /home/sjc/notify_boot.sh /home/sjc/telegram_bot.py

sudo cp provisioning/monitoring/notify-boot.service /etc/systemd/system/
sudo cp provisioning/monitoring/telegram-bot.service /etc/systemd/system/
sudo cp provisioning/monitoring/dreammachine-heartbeat.service /etc/systemd/system/
sudo cp provisioning/monitoring/dreammachine-heartbeat.timer /etc/systemd/system/

sudo systemctl daemon-reload
sudo systemctl enable --now telegram-bot.service
sudo systemctl enable notify-boot.service
sudo systemctl enable --now dreammachine-heartbeat.timer

echo "==> NOTE: requires /home/sjc/.email_password (Gmail App Password) for"
echo "    email delivery — Telegram works without it. Copy that file"
echo "    manually per-unit if not already present (not tracked in git)."
echo "==> Installed. Test now with:"
echo "    python3 /home/sjc/notify.py heartbeat"
