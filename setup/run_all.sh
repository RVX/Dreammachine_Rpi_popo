#!/usr/bin/env bash
# run_all.sh — orchestrator: runs setup 01-04 in order on a fresh Pi.
set -euo pipefail
cd "$(dirname "$0")"

for step in 01_system_base.sh 02_install_reaper.sh 03_led_service.sh 04_vnc_and_autostart.sh; do
    echo ""
    echo "########## ${step} ##########"
    bash "${step}"
done

echo ""
echo "All setup steps complete. Reboot to apply autologin/autostart/watchdog: sudo reboot"
