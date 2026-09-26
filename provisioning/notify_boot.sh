#!/bin/bash
# DREAMMACHINE boot notification
# Sends Telegram + email notification on every boot (after internet is up)

# Wait for actual internet connectivity (DNS + route), max 3 minutes.
# NOTE: 'tailscale ip -4' is NOT a valid check — it returns the local IP
# even when the Pi has no internet at all.
for i in $(seq 1 36); do
    if ping -c 1 -W 2 8.8.8.8 >/dev/null 2>&1 && getent hosts api.telegram.org >/dev/null 2>&1; then
        break
    fi
    sleep 5
done

# Send notification using Python script
if [ -f /home/sjc/notify.py ]; then
    python3 /home/sjc/notify.py
fi
