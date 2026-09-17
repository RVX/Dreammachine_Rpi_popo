#!/usr/bin/env bash
# run_all.sh — orchestrator: runs all setup steps in order on a fresh Pi.
set -euo pipefail
cd "$(dirname "$0")"

for step in 01_system_base.sh 01_audio_dac.sh 02_install_reaper.sh 04_vnc_and_autostart.sh 05_install_reaper_extensions.sh; do
    echo ""
    echo "########## ${step} ##########"
    bash "${step}"
done

echo ""
echo "All setup steps complete. Reboot to apply autologin/autostart/watchdog: sudo reboot"
