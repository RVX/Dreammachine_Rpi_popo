#!/bin/bash
# DREAMMACHINE Show-Hours Gate
# Mutes/unmutes the installation on a daily schedule (09:45 open, 23:00
# close) WITHOUT power-cycling the Pi or restarting REAPER itself — REAPER
# keeps its tracks looping in the background the whole time, only the amp
# and the LED output are gated. This avoids the reliability/SD-corruption
# risk of daily power cycling while still giving a clean, quiet "closed"
# state outside visiting hours.
#
# Usage: show_hours_gate.sh open|close
set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PATTERN="${REPO_DIR}/rp2350/pattern.py"
LOG=/var/log/dreammachine-show-hours.log

log() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') $1" | tee -a "$LOG"
}

case "${1:-}" in
    open)
        log "Show-hours OPEN: starting LEDs, unmuting amp"
        systemctl start dreammachine-led.service
        python3 "${PATTERN}" amp-unmute
        log "Show-hours OPEN complete"
        ;;
    close)
        log "Show-hours CLOSE: muting amp, stopping LEDs"
        python3 "${PATTERN}" amp-mute
        systemctl stop dreammachine-led.service
        log "Show-hours CLOSE complete"
        ;;
    *)
        echo "Usage: $0 open|close" >&2
        exit 1
        ;;
esac
