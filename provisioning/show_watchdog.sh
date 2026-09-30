#!/bin/bash
# DREAMMACHINE Show Watchdog
# The show (REAPER audio + LEDs) is the top priority of this installation —
# it must keep running 9:45-23:00 daily regardless of network status. This
# watchdog protects the one failure mode that lxsession's own "@" auto-restart
# CANNOT catch: an X11/Xorg HANG (not a crash/exit). A hung Xorg process is
# still "running" from lxsession's point of view, so nothing respawns REAPER
# — this exact failure was observed in the field on dm3. The known-good manual
# fix (see provisioning/debug_autostart.sh) is `systemctl restart lightdm`;
# this script automates that, and only reboots if that doesn't bring the show
# back either.
#
# This script NEVER looks at network/internet status. It only cares whether
# REAPER is actually running. It is deliberately independent from and
# complementary to network_watchdog.sh, which now defers to this script's
# definition of "show healthy" before ever rebooting for network reasons.
#
# Every external call is wrapped in `timeout` for the same reason as
# network_watchdog.sh: a watchdog that can itself hang defeats its purpose.

LOG=/var/log/dreammachine-show-watchdog.log
CHECK_INTERVAL=30            # seconds between checks
DOWN_THRESHOLD=6              # ~3 min of REAPER not running -> try lightdm restart
LIGHTDM_RECOVERY_GRACE=120     # seconds to wait after restarting lightdm before rechecking
MAX_LIGHTDM_ATTEMPTS=2        # how many lightdm restarts to try before rebooting
BOOT_SETTLE_SECONDS=150       # ignore failures for this long after watchdog start (X + lxsession + start_reaper.sh + REAPER load time)

FAIL_COUNT=0
LIGHTDM_ATTEMPTS=0

log() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') $1" | tee -a "$LOG"
}

reaper_running() {
    pgrep -x reaper >/dev/null 2>&1
}

log "Show watchdog started, settling for ${BOOT_SETTLE_SECONDS}s before monitoring"
sleep "$BOOT_SETTLE_SECONDS"
log "Show watchdog entering monitor loop"

while true; do
    if reaper_running; then
        if [ "$FAIL_COUNT" -gt 0 ]; then
            log "REAPER is running again after $FAIL_COUNT failed check(s)"
        fi
        FAIL_COUNT=0
        LIGHTDM_ATTEMPTS=0
    else
        FAIL_COUNT=$((FAIL_COUNT + 1))
        log "REAPER not running ($FAIL_COUNT consecutive check(s))"

        if [ "$FAIL_COUNT" -ge "$DOWN_THRESHOLD" ]; then
            if [ "$LIGHTDM_ATTEMPTS" -lt "$MAX_LIGHTDM_ATTEMPTS" ]; then
                LIGHTDM_ATTEMPTS=$((LIGHTDM_ATTEMPTS + 1))
                log "REAPER down for $((DOWN_THRESHOLD * CHECK_INTERVAL / 60)) min — restarting lightdm (attempt ${LIGHTDM_ATTEMPTS}/${MAX_LIGHTDM_ATTEMPTS}), this recovers a hung X session"
                timeout 30 systemctl restart lightdm
                FAIL_COUNT=0
                log "Waiting ${LIGHTDM_RECOVERY_GRACE}s for desktop session + REAPER to come back up"
                sleep "$LIGHTDM_RECOVERY_GRACE"
                continue
            else
                log "REAPER still down after ${MAX_LIGHTDM_ATTEMPTS} lightdm restarts — rebooting as last resort (show is confirmed down, reboot is now justified)"
                reboot
            fi
        fi
    fi
    sleep "$CHECK_INTERVAL"
done
