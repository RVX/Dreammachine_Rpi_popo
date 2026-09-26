#!/bin/bash
# DREAMMACHINE USB WiFi Config Reader
# Watches for USB drive with dreammachine-wifi.txt and applies config

WATCH_DIR="/media/sjc"
CONFIG_FILE="dreammachine-wifi.txt"
DONE_MARKER="/home/sjc/.wifi_configured"

# Already configured? Exit.
if [ -f "$DONE_MARKER" ]; then
    exit 0
fi

log() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') $1" | tee -a /var/log/dreammachine-usb.log
}

log "USB WiFi config watcher started"

while true; do
    # Look for mounted USB drives
    for mount in "$WATCH_DIR"/*; do
        if [ -d "$mount" ] && [ -f "$mount/$CONFIG_FILE" ]; then
            log "Found $CONFIG_FILE on $mount"
            
            # Parse config
            SSID=$(grep -i "^SSID=" "$mount/$CONFIG_FILE" | cut -d= -f2- | tr -d '\r\n')
            PASSWORD=$(grep -i "^PASSWORD=" "$mount/$CONFIG_FILE" | cut -d= -f2- | tr -d '\r\n')
            
            if [ -n "$SSID" ] && [ -n "$PASSWORD" ]; then
                log "Configuring WiFi: $SSID"
                
                # Delete old connection if exists
                nmcli connection delete "$SSID" 2>/dev/null
                
                # Add new connection
                if nmcli connection add type wifi ifname wlan0 con-name "$SSID" ssid "$SSID" wifi-sec.key-mgmt wpa-psk wifi-sec.psk "$PASSWORD"; then
                    # Try to connect
                    if nmcli connection up "$SSID" timeout 15; then
                        log "Connected to $SSID successfully"
                        touch "$DONE_MARKER"
                        
                        # Safely eject USB
                        umount "$mount" 2>/dev/null
                        log "USB ejected. Remove the drive."
                        
                        # Exit (we're done)
                        exit 0
                    else
                        log "ERROR: Failed to connect to $SSID"
                    fi
                else
                    log "ERROR: Failed to create connection profile"
                fi
            else
                log "ERROR: Invalid config file format. Expected: SSID=name and PASSWORD=pass"
            fi
        fi
    done
    
    sleep 5
done
