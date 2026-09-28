#!/bin/bash
# DREAMMACHINE remote update — pulls latest code and flashes RP2350 if changed.
# Triggered by Telegram /update, or manually over SSH.
# Logs to /var/log/dreammachine-update.log; prints a summary line for the caller.

set -u
set -o pipefail
REPO_DIR="/home/sjc/dreammachine"
LOG="/var/log/dreammachine-update.log"
SUMMARY=""

log() { echo "$(date '+%Y-%m-%d %H:%M:%S') $1" | sudo tee -a "$LOG" >/dev/null; }

# Trap unexpected errors and report them
trap 'echo "UPDATE-FAIL: line $LINENO exited with code $?"; log "TRAP: line $LINENO code $?"' ERR

cd "$REPO_DIR" || { echo "UPDATE-FAIL: repo not found at $REPO_DIR"; exit 1; }

# --- 1. Git pull (software) ---
BEFORE=$(git rev-parse --short HEAD 2>/dev/null || echo "none")
if ! git pull --ff-only >/tmp/dm-pull.log 2>&1; then
    PULL_ERR=$(tail -1 /tmp/dm-pull.log 2>/dev/null || echo "unknown")
    log "git pull FAILED: $PULL_ERR"
    echo "UPDATE-FAIL: git pull failed — $PULL_ERR"
    exit 1
fi
AFTER=$(git rev-parse --short HEAD 2>/dev/null || echo "unknown")

if [ "$BEFORE" = "$AFTER" ]; then
    log "already up to date ($AFTER)"
    echo "UPDATE-OK: already up to date ($AFTER)"
    exit 0
fi

log "updated $BEFORE -> $AFTER"
SUMMARY="code $BEFORE->$AFTER"

# --- 2. Sync deployed files that live outside the repo ---
CHANGED=$(git diff --name-only "$BEFORE" "$AFTER")

# notify/telegram bot live in /home/sjc
for f in notify.py telegram_bot.py notify_boot.sh; do
    if echo "$CHANGED" | grep -q "provisioning/$f"; then
        sed -i 's/\r$//' "provisioning/$f"
        cp "provisioning/$f" "/home/sjc/$f"
        chmod +x "/home/sjc/$f"
        log "deployed $f"
        SUMMARY="$SUMMARY, $f"
    fi
done

# Always ensure scripts are executable (git on Windows loses +x bit)
chmod +x systemd/start_reaper.sh rp2350/pattern.py 2>/dev/null || true

# REAPER scripts and support files
if echo "$CHANGED" | grep -q "reaper/"; then
    for f in reaper/ensure_reaper_audio.sh reaper/force_master_mono.lua reaper/__startup.lua reaper/DM_Autoloop_Tracks_1-4.lua reaper/DM_Sonifications_Tracks_5-10.lua; do
        if [ -f "$f" ]; then
            cp "$f" /home/sjc/.config/REAPER/Scripts/ 2>/dev/null || true
        fi
    done
    if [ -f reaper/ensure_reaper_audio.sh ]; then
        cp reaper/ensure_reaper_audio.sh /home/sjc/dreammachine/reaper/
        chmod +x /home/sjc/dreammachine/reaper/ensure_reaper_audio.sh
    fi
    log "reaper files updated"
    SUMMARY="$SUMMARY, reaper-updated"
fi

# LED controller (runs from repo dir, just needs restart)
if echo "$CHANGED" | grep -q "led/led_controller_spi.py"; then
    sudo systemctl restart dreammachine-led.service
    log "restarted dreammachine-led"
    SUMMARY="$SUMMARY, led-restarted"
fi

# --- 3. RP2350 firmware flash (only if the .elf changed) ---
if echo "$CHANGED" | grep -q "rp2350/build/dreammachine_rp2350.elf"; then
    if [ "${FIRMWARE_AUTOUPDATE:-0}" = "1" ]; then
        log "RP2350 firmware changed, flashing..."
        if sudo openocd -f rp2350/rpi4-rp2350-swd.cfg \
                -f target/rp2350.cfg \
                -c "program rp2350/build/dreammachine_rp2350.elf verify reset exit" \
                >> "$LOG" 2>&1; then
            log "RP2350 flash OK"
            SUMMARY="$SUMMARY, RP2350-flashed"
        else
            log "RP2350 flash FAILED"
            echo "UPDATE-PARTIAL: $SUMMARY but RP2350 flash FAILED"
            exit 2
        fi
    else
        log "RP2350 firmware changed but FIRMWARE_AUTOUPDATE=0, skipping flash"
        SUMMARY="$SUMMARY, RP2350-pending(/flash to apply)"
    fi
fi

# --- 4. Restart telegram bot if it changed ---
if echo "$CHANGED" | grep -q "provisioning/telegram_bot.py"; then
    sudo systemctl restart telegram-bot.service
    log "restarted telegram-bot"
fi

log "update complete: $SUMMARY"
echo "UPDATE-OK: $SUMMARY"
