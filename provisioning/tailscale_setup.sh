#!/bin/bash
# DREAMMACHINE Tailscale auto-join
# Runs on first boot after WiFi is configured
# Joins the Pi to the Tailnet for remote access from anywhere

set -e

AUTH_KEY="tskey-auth-krgtTx2qEZ11CNTRL-FSuzLc4JU3GL7TdpEx3N3GwLfhjXzNBZ"
HOSTNAME=$(hostname)

log() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') $1" | tee -a /var/log/dreammachine-tailscale.log
}

# Skip if already joined
if tailscale status >/dev/null 2>&1; then
    log "Tailscale already connected, skipping"
    exit 0
fi

log "Installing Tailscale..."
curl -fsSL https://tailscale.com/install.sh | sh

log "Joining Tailnet as $HOSTNAME..."
tailscale up --authkey="$AUTH_KEY" --hostname="$HOSTNAME" --accept-routes

log "Tailscale connected"
tailscale ip -4

# Optional: Enable Tailscale SSH (allows SSH without local SSH keys)
# tailscale set --ssh
