#!/usr/bin/env bash
# 04_vnc_and_autostart.sh — remote GUI access (VNC) + unattended kiosk boot.
# Run on the Pi: bash setup/04_vnc_and_autostart.sh
# NOTE: reboot at the end to apply autologin/watchdog changes.
set -euo pipefail
cd "$(dirname "$0")/.."
source config/dreammachine.env

VNC_PASSWORD="${VNC_PASSWORD:-sjcsjc}"

echo "==> enabling RealVNC server"
sudo raspi-config nonint do_vnc 0
printf '%s\n%s\n' "${VNC_PASSWORD}" "${VNC_PASSWORD}" | sudo vncpasswd -service || \
    echo "WARNING: vncpasswd -service failed, set the VNC password manually."
sudo systemctl enable --now vncserver-x11-serviced || true

echo "==> enabling desktop autologin (kiosk boot, no keyboard/monitor needed)"
sudo raspi-config nonint do_boot_behaviour B4

echo "==> enabling Raspberry Pi hardware watchdog (auto-reboot if the system hangs)"
CONFIG_TXT=/boot/firmware/config.txt
if ! grep -q '^dtparam=watchdog=on' "${CONFIG_TXT}" 2>/dev/null; then
    echo 'dtparam=watchdog=on' | sudo tee -a "${CONFIG_TXT}" >/dev/null
fi
if ! grep -q '^RuntimeWatchdogSec=' /etc/systemd/system.conf 2>/dev/null; then
    echo 'RuntimeWatchdogSec=15' | sudo tee -a /etc/systemd/system.conf >/dev/null
fi

echo "==> configuring REAPER autostart on desktop login (labwc)"
AUTOSTART_DIR="${HOME}/.config/labwc"
mkdir -p "${AUTOSTART_DIR}"
AUTOSTART_FILE="${AUTOSTART_DIR}/autostart"
touch "${AUTOSTART_FILE}"
MARKER="# --- DREAMMACHINE autostart ---"
if ! grep -qF "${MARKER}" "${AUTOSTART_FILE}"; then
    cat >>"${AUTOSTART_FILE}" <<EOF

${MARKER}
# Wait for the desktop/audio stack to settle, then launch REAPER with the project.
(
  sleep 8
  /usr/local/bin/reaper "${REAPER_PROJECT_PATH}" &
) &
EOF
fi

echo "04_vnc_and_autostart.sh done. Reboot to apply: sudo reboot"
