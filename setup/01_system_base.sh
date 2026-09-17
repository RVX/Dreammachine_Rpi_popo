#!/usr/bin/env bash
# 01_system_base.sh — base OS packages + gpiozero/lgpio + ALSA default device.
# Run on the Pi as the sjc user: bash setup/01_system_base.sh
set -euo pipefail
cd "$(dirname "$0")/.."
source config/dreammachine.env

echo "==> apt update/upgrade"
sudo apt update
sudo apt -y full-upgrade

echo "==> installing base packages"
# NOTE: Debian Trixie no longer packages pigpio/pigpiod (upstream pigpio is
# unmaintained and doesn't support the newer GPIO chip driver model). The
# Raspberry Pi Foundation's supported replacement is lgpio/gpiozero, which
# ships preinstalled on the desktop image but we install explicitly here for
# robustness on a from-scratch Pi.
sudo apt -y install \
    python3-gpiozero python3-lgpio python3-rpi-lgpio \
    python3-venv python3-pip \
    alsa-utils \
    git curl

echo "01_system_base.sh done."
echo "NEXT: run setup/01_audio_dac.sh to configure the custom PCM5102A shield."
