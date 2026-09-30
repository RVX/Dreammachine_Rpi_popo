#!/bin/bash
# DREAMMACHINE Network Watchdog
# Detects sustained network loss (e.g. NetworkManager/wlan0 driver hang) and
# self-heals: restart NetworkManager -> reboot as last resort.
# This targets units that were connected fine for a long time and then went
# fully unreachable (WiFi + Tailscale + RustDesk all dead) — a hung network
# stack, not a missing-credentials problem (see wifi-portal for that case).

LOG=/var/log/dreammachine-network-watchdog.log
CHECK_INTERVAL=30     # seconds between checks
RESTART_NM_AFTER=4    # ~2 min of consecutive failures -> restart NetworkManager
REBOOT_AFTER=20       # ~10 min of consecutive failures -> reboot as last resort

FAIL_COUNT=0
NM_RESTARTED=0

log() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') $1" | tee -a "$LOG"
}

has_connectivity() {
    ip route show default | grep -q default || return 1
    timeout 5 ping -c1 -W3 1.1.1.1 >/dev/null 2>&1 && return 0
    timeout 5 ping -c1 -W3 8.8.8.8 >/dev/null 2>&1 && return 0
    return 1
}

log "Network watchdog started"

while true; do
    if has_connectivity; then
        if [ "$FAIL_COUNT" -gt 0 ]; then
            log "Connectivity restored after $FAIL_COUNT failed check(s)"
        fi
        FAIL_COUNT=0
        NM_RESTARTED=0
    else
        FAIL_COUNT=$((FAIL_COUNT + 1))
        log "Connectivity check failed ($FAIL_COUNT consecutive)"

        if [ "$FAIL_COUNT" -eq "$RESTART_NM_AFTER" ] && [ "$NM_RESTARTED" -eq 0 ]; then
            log "Restarting NetworkManager (recovery attempt)"
            systemctl restart NetworkManager
            NM_RESTARTED=1
        fi

        if [ "$FAIL_COUNT" -ge "$REBOOT_AFTER" ]; then
            log "Network still down $((REBOOT_AFTER * CHECK_INTERVAL / 60)) min after NetworkManager restart — rebooting as last resort"
            reboot
        fi
    fi
    sleep "$CHECK_INTERVAL"
done
