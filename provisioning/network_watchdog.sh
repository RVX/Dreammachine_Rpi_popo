#!/bin/bash
# DREAMMACHINE Network Watchdog
# Detects sustained network loss (e.g. NetworkManager/wlan0 driver hang) and
# self-heals: restart NetworkManager -> reboot as last resort.
# This targets units that were connected fine for a long time and then went
# fully unreachable (WiFi + Tailscale + RustDesk all dead) — a hung network
# stack, not a missing-credentials problem (see wifi-portal for that case).
#
# Interaction with wifi-portal's recovery hotspot: while the "Hotspot" NM
# connection is active, this watchdog defers to it for a grace period
# (HOTSPOT_GRACE_SECONDS) so an on-site person has a real window to fix
# WiFi via the captive portal, instead of the watchdog restarting
# NetworkManager or rebooting out from under them mid-session. If nobody
# fixes it within the grace period, escalation resumes — a stack hang
# (this unit's actual observed failure: credentials were already correct,
# NetworkManager just hung) looks identical to "no known network" from the
# portal's point of view, and only a NetworkManager restart/reboot fixes
# that, not new credentials. Without this resumption, a hung-stack incident
# would leave the hotspot open forever with nobody able to fix it, blocking
# the one recovery action we've confirmed actually works.
#
# Every external call is wrapped in `timeout` — a watchdog that can itself
# hang defeats its purpose, especially since D-Bus/NetworkManager calls are
# exactly what may be wedged during the failure this script exists to fix.

LOG=/var/log/dreammachine-network-watchdog.log
CHECK_INTERVAL=30           # seconds between checks
RESTART_NM_AFTER=4          # ~2 min of consecutive failures -> restart NetworkManager
REBOOT_AFTER=20             # ~10 min of consecutive failures -> reboot as last resort
HOTSPOT_GRACE_SECONDS=480   # ~8 min grace once the recovery hotspot is up

FAIL_COUNT=0
NM_RESTARTED=0
HOTSPOT_SINCE_FILE=/tmp/.dreammachine_hotspot_since

log() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') $1" | tee -a "$LOG"
}

has_connectivity() {
    ip route show default 2>/dev/null | grep -q default || return 1
    timeout 5 ping -c1 -W3 1.1.1.1 >/dev/null 2>&1 && return 0
    timeout 5 ping -c1 -W3 8.8.8.8 >/dev/null 2>&1 && return 0
    return 1
}

hotspot_active() {
    timeout 5 nmcli -t -f NAME connection show --active 2>/dev/null | grep -qx "Hotspot"
}

log "Network watchdog started"

while true; do
    if has_connectivity; then
        if [ "$FAIL_COUNT" -gt 0 ]; then
            log "Connectivity restored after $FAIL_COUNT failed check(s)"
        fi
        FAIL_COUNT=0
        NM_RESTARTED=0
        rm -f "$HOTSPOT_SINCE_FILE"
    elif hotspot_active; then
        now=$(date +%s)
        [ -f "$HOTSPOT_SINCE_FILE" ] || echo "$now" > "$HOTSPOT_SINCE_FILE"
        since=$(cat "$HOTSPOT_SINCE_FILE" 2>/dev/null || echo "$now")
        elapsed=$((now - since))
        if [ "$elapsed" -lt "$HOTSPOT_GRACE_SECONDS" ]; then
            log "Recovery hotspot active for ${elapsed}s (< ${HOTSPOT_GRACE_SECONDS}s grace) — deferring to wifi-portal"
            FAIL_COUNT=0
        else
            log "Recovery hotspot open ${elapsed}s with no fix — resuming watchdog escalation"
            FAIL_COUNT=$((FAIL_COUNT + 1))
        fi
    else
        rm -f "$HOTSPOT_SINCE_FILE"
        FAIL_COUNT=$((FAIL_COUNT + 1))
        log "Connectivity check failed ($FAIL_COUNT consecutive)"

        if [ "$FAIL_COUNT" -eq "$RESTART_NM_AFTER" ] && [ "$NM_RESTARTED" -eq 0 ]; then
            log "Restarting NetworkManager (recovery attempt)"
            timeout 30 systemctl restart NetworkManager
            NM_RESTARTED=1
        fi

        if [ "$FAIL_COUNT" -ge "$REBOOT_AFTER" ]; then
            log "Network still down $((REBOOT_AFTER * CHECK_INTERVAL / 60)) min after NetworkManager restart — rebooting as last resort"
            reboot
        fi
    fi
    sleep "$CHECK_INTERVAL"
done
