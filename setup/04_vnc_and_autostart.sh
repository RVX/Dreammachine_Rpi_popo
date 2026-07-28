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

echo "==> switching desktop session to X11 (Openbox) instead of labwc/Wayland"
# REAPER is an X11-only app; under the default labwc/Wayland session it runs via
# XWayland, and drag-and-drop between XWayland and native Wayland apps (e.g. the
# file manager) is unreliable on wlroots-based compositors like labwc. Running a
# plain X11 session avoids that bridging problem entirely (Insert Media still
# works either way, but this restores drag-and-drop too).
sudo raspi-config nonint do_wayland W1

echo "==> enabling Raspberry Pi hardware watchdog (auto-reboot if the system hangs)"
CONFIG_TXT=/boot/firmware/config.txt
if ! grep -q '^dtparam=watchdog=on' "${CONFIG_TXT}" 2>/dev/null; then
    echo 'dtparam=watchdog=on' | sudo tee -a "${CONFIG_TXT}" >/dev/null
fi
if ! grep -q '^RuntimeWatchdogSec=' /etc/systemd/system.conf 2>/dev/null; then
    echo 'RuntimeWatchdogSec=15' | sudo tee -a /etc/systemd/system.conf >/dev/null
fi

echo "==> configuring REAPER autostart on desktop login (X11 / lxsession rpd-x)"
DREAMMACHINE_DIR="$(cd "$(dirname "$0")/.." && pwd)"
START_SCRIPT="${DREAMMACHINE_DIR}/systemd/start_reaper.sh"
cat >"${START_SCRIPT}" <<EOF
#!/usr/bin/env bash
# Launches REAPER after a short delay to let the desktop/audio stack settle.
# Used as an lxsession (rpd-x/X11) autostart entry.
sleep 8
exec /usr/local/bin/reaper "${REAPER_PROJECT_PATH}"
EOF
chmod +x "${START_SCRIPT}"

LXSESSION_DIR="${HOME}/.config/lxsession/rpd-x"
mkdir -p "${LXSESSION_DIR}"
cat >"${LXSESSION_DIR}/autostart" <<EOF
@lxpanel-pi
@pcmanfm-pi
@xscreensaver -no-splash
@${START_SCRIPT}
EOF

echo "04_vnc_and_autostart.sh done. Reboot to apply: sudo reboot"
