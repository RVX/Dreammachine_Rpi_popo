#!/usr/bin/env bash
# 03_led_service.sh — python venv + systemd service for the LED controller.
# Run on the Pi: bash setup/03_led_service.sh
set -euo pipefail
cd "$(dirname "$0")/.."
REPO_DIR="$(pwd)"

echo "==> creating venv at led/venv (--system-site-packages to inherit apt's gpiozero/lgpio)"
python3 -m venv --system-site-packages led/venv
led/venv/bin/pip install --upgrade pip
led/venv/bin/pip install -r led/requirements.txt

echo "==> installing systemd unit"
# Rewrite the hardcoded /home/sjc/dreammachine paths in the unit file to match
# wherever this repo actually lives, in case it's deployed elsewhere.
sed "s#/home/sjc/dreammachine#${REPO_DIR}#g" systemd/dreammachine-led.service \
    | sudo tee /etc/systemd/system/dreammachine-led.service >/dev/null

sudo systemctl daemon-reload
sudo systemctl enable dreammachine-led.service
sudo systemctl restart dreammachine-led.service

echo "==> status:"
sudo systemctl status dreammachine-led.service --no-pager || true

echo "03_led_service.sh done."
