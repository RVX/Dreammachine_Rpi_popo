#!/bin/bash
# DREAMMACHINE Tailscale join notification
# Sends Telegram + email when a Pi joins the Tailnet

TELEGRAM_TOKEN="8628742544:AAH80zdbP4OYtj0DSSDkUDj3Q9784K8cxXI"
TELEGRAM_CHAT_ID="350553264"

HOSTNAME=$(hostname)
TAILSCALE_IP=$(tailscale ip -4 2>/dev/null || echo "unknown")
PUBLIC_IP=$(curl -s --max-time 5 ifconfig.me || echo "unknown")
UPTIME=$(uptime -p | sed 's/up //')
TIMESTAMP=$(date -u '+%Y-%m-%d %H:%M:%S UTC')

# Get local network info
LOCAL_IP=$(ip -4 addr show wlan0 2>/dev/null | grep -oP 'inet \K[\d.]+' || echo "not connected")
WIFI_SSID=$(nmcli -t -f NAME,DEVICE,STATE connection show --active 2>/dev/null | grep wlan0 | cut -d: -f1 || echo "unknown")

# Get RustDesk ID if available
RUSTDESK_ID=$(sudo -u sjc rustdesk --get-id 2>/dev/null || echo "not installed")

# Build message
MESSAGE="🟢 <b>DREAMMACHINE Unit Online</b>

<b>Unit:</b> $HOSTNAME
<b>Tailscale IP:</b> $TAILSCALE_IP
<b>Local Network:</b> $WIFI_SSID ($LOCAL_IP)
<b>Public IP:</b> $PUBLIC_IP
<b>Uptime:</b> $UPTIME
<b>Time:</b> $TIMESTAMP

<b>Access:</b>
SSH: <code>ssh sjc@$TAILSCALE_IP</code>
RustDesk ID: <code>$RUSTDESK_ID</code>"

# Send Telegram notification
curl -s -X POST "https://api.telegram.org/bot${TELEGRAM_TOKEN}/sendMessage" \
  -d chat_id="$TELEGRAM_CHAT_ID" \
  -d text="$MESSAGE" \
  -d parse_mode="HTML" \
  > /dev/null 2>&1

echo "$(date '+%Y-%m-%d %H:%M:%S') Notification sent for $HOSTNAME" >> /var/log/dreammachine-notify.log
