#!/bin/bash
# DREAMMACHINE boot notification
# Sends Telegram + email notification on every boot (after Tailscale connects)

# Wait for Tailscale to be ready (max 60s)
for i in $(seq 1 12); do
    if tailscale ip -4 >/dev/null 2>&1; then
        break
    fi
    sleep 5
done

# Send notification using Python script
if [ -f /home/sjc/notify.py ]; then
    python3 /home/sjc/notify.py
fi
