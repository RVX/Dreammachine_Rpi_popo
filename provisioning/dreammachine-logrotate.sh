#!/bin/bash
# dreammachine-logrotate — keep logs small, prevent SD card fill-up.
# Called by cron daily. Truncates any log over 1MB, deletes anything over 10MB.

LOGS=(
    /var/log/dreammachine-notify.log
    /var/log/dreammachine-tailscale.log
    /var/log/dreammachine-update.log
    /var/log/dreammachine-usb.log
    /var/log/dreammachine-firstboot.log
    /tmp/popo_live.log
    /tmp/start_reaper.log
)

for f in "${LOGS[@]}"; do
    [ -f "$f" ] || continue
    size=$(stat -c%s "$f" 2>/dev/null || echo 0)
    if [ "$size" -gt 10485760 ]; then
        # Over 10MB — keep last 1000 lines
        tail -1000 "$f" > "${f}.tmp" && mv "${f}.tmp" "$f"
        logger -t dreammachine "Log $f truncated (was ${size} bytes)"
    elif [ "$size" -gt 1048576 ]; then
        # Over 1MB — keep last 5000 lines
        tail -5000 "$f" > "${f}.tmp" && mv "${f}.tmp" "$f"
    fi
done

# Limit systemd journal to 50MB
journalctl --vacuum-size=50M > /dev/null 2>&1

# Clean old POPO wav files (script already prunes with --keep-days, belt+braces)
find /home/sjc/popo/datasets/ground/sonifications/ -name "popo_live_*" -mtime +7 -delete 2>/dev/null
find /home/sjc/popo/datasets/ground/mseed/ -name "popo_live_*" -mtime +7 -delete 2>/dev/null

# REAPER auto-save backups grow forever with no built-in rotation; keep 14
# days of undo history, prune the rest (nothing else touches this folder)
find /home/sjc/reaper-projects/*/Backups/ -type f \( -name "*.rpp-bak" -o -name "*.RPP" \) -mtime +14 -delete 2>/dev/null

# Log disk usage
df -h / | tail -1 | logger -t dreammachine-disk
