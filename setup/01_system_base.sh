#!/usr/bin/env bash
# 01_system_base.sh — base OS packages + pigpio + ALSA default device.
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

echo "==> setting Audio+ (${ALSA_CARD_NAME}) as default ALSA device"
CARD_NUM=$(aplay -l | awk -v name="${ALSA_CARD_NAME}" '$0 ~ name {print $2}' | tr -d ':' | head -n1)
if [ -z "${CARD_NUM}" ]; then
    echo "WARNING: could not find ALSA card '${ALSA_CARD_NAME}' — is the shield plugged in?" >&2
else
    sudo tee /etc/asound.conf >/dev/null <<EOF
pcm.!default {
    type plug
    slave.pcm "hw:${CARD_NUM},0"
}
ctl.!default {
    type hw
    card ${CARD_NUM}
}
EOF
    echo "Default ALSA device set to hw:${CARD_NUM},0 (${ALSA_CARD_NAME})"
fi

echo "==> quick sound test (5x front-left/front-right on the shield)"
speaker-test -D default -l1 -c2 -t wav || echo "speaker-test failed, check wiring"

echo "01_system_base.sh done."
