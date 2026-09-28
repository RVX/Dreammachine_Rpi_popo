#!/bin/bash
# provision_unit.sh v2 — One-shot DREAMMACHINE unit provisioning.
# Fixes all issues found on sjcdm2/sjcdm3 bring-up:
# - .elf firmware + REAPER tarball + extensions + RustDesk as /tmp assets
# - REAPER symlink handles both flat and nested /opt/REAPER layouts
# - dpkg lock from packagekitd killed first
# - RustDesk installed with per-unit password
# - RPP references fixed to local POPO wavs
# - lxsession autostart made executable
#
# Usage: scp assets to /tmp/, then:
#   ssh sjc@<ip> 'bash /tmp/provision_unit.sh 5'
# Required /tmp/ assets: reaper.tar.xz, reaper_sws-aarch64.so,
#   reaper_reapack-aarch64.so, rustdesk-aarch64.deb, dreammachine_rp2350.elf

set -uo pipefail
UNIT_NUM="${1:?Usage: provision_unit.sh <unit_number> (e.g. 2, 3, 5)}"
HOSTNAME="sjcdm${UNIT_NUM}"
POPO_STAGGER=$((UNIT_NUM * 10))
REPO="https://github.com/RVX/Dreammachine_Rpi_popo.git"
TAILSCALE_KEY="tskey-auth-krgtTx2qEZ11CNTRL-FSuzLc4JU3GL7TdpEx3N3GwLfhjXzNBZ"
EMAIL_PASSWORD="sxiterhlujuyrbtm"
SSH_KEY="ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIHtzs5WjIRKy5zZnc0z1GGvKBjFVIf1vCukw6QWqtX9G dreammachine-pi"
RUSTDESK_PASSWORD="OMRdream${UNIT_NUM}"
ERRORS=""

log() { echo "[$(date '+%H:%M:%S')] $1"; }
fail() { ERRORS="$ERRORS\n  - $1"; log "FAIL: $1"; }

# Kill packagekit if holding dpkg lock
pkill -f packagekitd 2>/dev/null || true

# --- 1. Hostname + SSH key + autologin + session ---
log "Setting hostname to $HOSTNAME..."
echo sjcsjc | sudo -S hostnamectl set-hostname "$HOSTNAME" 2>/dev/null || fail "hostname"
echo sjcsjc | sudo -S sed -i "s/127.0.1.1.*/127.0.1.1\t$HOSTNAME/" /etc/hosts 2>/dev/null
mkdir -p ~/.ssh
grep -q "dreammachine-pi" ~/.ssh/authorized_keys 2>/dev/null || echo "$SSH_KEY" >> ~/.ssh/authorized_keys
chmod 700 ~/.ssh; chmod 600 ~/.ssh/authorized_keys
echo sjcsjc | sudo -S systemctl enable ssh 2>/dev/null
# Desktop autologin + force rpd-x (X11) session — labwc uses different autostart format
echo sjcsjc | sudo -S raspi-config nonint do_boot_behaviour B4 2>/dev/null || fail "autologin"
echo sjcsjc | sudo -S sed -i 's/^user-session=.*/user-session=rpd-x/; s/^autologin-session=.*/autologin-session=rpd-x/; s/^greeter-session=.*/greeter-session=pi-greeter-x/' /etc/lightdm/lightdm.conf 2>/dev/null || fail "session"

# --- 2. Tailscale ---
if ! tailscale ip -4 >/dev/null 2>&1; then
    log "Installing Tailscale..."
    curl -fsSL https://tailscale.com/install.sh | sh 2>&1 | tail -1
    echo sjcsjc | sudo -S tailscale up --authkey="$TAILSCALE_KEY" --hostname="$HOSTNAME" --accept-routes || fail "tailscale"
fi
TS_IP=$(tailscale ip -4 2>/dev/null || echo "pending")
log "Tailscale: $TS_IP"

# --- 3. Repo ---
if [ ! -d /home/sjc/dreammachine/.git ]; then
    log "Cloning repo..."
    rm -rf /home/sjc/dreammachine
    git clone -q "$REPO" /home/sjc/dreammachine || fail "repo clone"
fi
cd /home/sjc/dreammachine && git pull --ff-only -q 2>/dev/null || true
echo sjcsjc | sudo -S chown -R sjc:sjc /home/sjc/dreammachine

# --- 4. System packages ---
log "Installing packages..."
echo sjcsjc | sudo -S apt install -y -qq openocd python3-pip python3-venv curl figlet avahi-daemon 2>&1 | tail -1
pip3 install --user --break-system-packages -q obspy python-osc spidev 2>&1 | tail -1

# --- 5. REAPER ---
REAPER_BIN=""
for p in /opt/REAPER/reaper /opt/REAPER/REAPER/reaper; do
    [ -f "$p" ] && REAPER_BIN="$p" && break
done
if [ -z "$REAPER_BIN" ]; then
    if [ -f /tmp/reaper.tar.xz ]; then
        log "Installing REAPER from /tmp/reaper.tar.xz..."
        echo sjcsjc | sudo -S tar xf /tmp/reaper.tar.xz -C /opt/ || fail "reaper extract"
        REAPER_BIN=$(find /opt -name reaper -type f 2>/dev/null | head -1)
    else
        fail "reaper tarball missing from /tmp"
    fi
fi
[ -n "$REAPER_BIN" ] && echo sjcsjc | sudo -S ln -sf "$REAPER_BIN" /usr/local/bin/reaper
log "REAPER: ${REAPER_BIN:-not found}"

# --- 6. REAPER extensions ---
mkdir -p ~/.config/REAPER/UserPlugins ~/.config/REAPER/Scripts
for ext in reaper_sws-aarch64.so reaper_reapack-aarch64.so; do
    if [ ! -f ~/.config/REAPER/UserPlugins/"$ext" ] && [ -f /tmp/"$ext" ]; then
        cp /tmp/"$ext" ~/.config/REAPER/UserPlugins/
        log "Installed $ext"
    fi
done

# --- 7. RustDesk ---
if ! which rustdesk >/dev/null 2>&1; then
    if [ -f /tmp/rustdesk-aarch64.deb ]; then
        log "Installing RustDesk..."
        echo sjcsjc | sudo -S dpkg -i /tmp/rustdesk-aarch64.deb 2>&1 | tail -1
        echo sjcsjc | sudo -S apt install -f -y -qq 2>&1 | tail -1
    else
        fail "rustdesk deb missing from /tmp"
    fi
fi
echo sjcsjc | sudo -S systemctl enable rustdesk 2>/dev/null
echo sjcsjc | sudo -S systemctl start rustdesk 2>/dev/null
sleep 3
echo sjcsjc | sudo -S rustdesk --password "$RUSTDESK_PASSWORD" 2>/dev/null
echo sjcsjc | sudo -S rustdesk --option direct-server Y 2>/dev/null
echo sjcsjc | sudo -S rustdesk --option verification-method use-permanent-password 2>/dev/null
RD_ID=$(echo sjcsjc | sudo -S rustdesk --get-id 2>/dev/null || echo "pending")
log "RustDesk: $RD_ID (password: $RUSTDESK_PASSWORD)"

# --- 8. REAPER project + config from golden master ---
GM="/home/sjc/dreammachine/golden-master/sjcdm4/dm-state"
mkdir -p ~/reaper-projects/Dreammachine_popo_01
if [ -d "$GM" ]; then
    cp "$GM/Dreammachine_popo_01.RPP" ~/reaper-projects/Dreammachine_popo_01/
    cp "$GM/reaper.ini" ~/.config/REAPER/
    cp "$GM/reaper-kb.ini" ~/.config/REAPER/
    cp "$GM/Scripts/DM_Autoloop_Tracks_1-4.lua" "$GM/Scripts/DM_Sonifications_Tracks_5-10.lua" "$GM/Scripts/__startup.lua" ~/.config/REAPER/Scripts/
    cp "$GM/ensure_reaper_audio.sh" /home/sjc/dreammachine/reaper/
    chmod +x /home/sjc/dreammachine/reaper/ensure_reaper_audio.sh
    log "Golden master deployed"
fi

# --- 9. Notifications ---
cp provisioning/notify.py provisioning/telegram_bot.py provisioning/notify_boot.sh provisioning/dm_update.sh /home/sjc/
chmod +x /home/sjc/notify.py /home/sjc/telegram_bot.py /home/sjc/notify_boot.sh /home/sjc/dm_update.sh
echo -n "$EMAIL_PASSWORD" > /home/sjc/.email_password
chmod 600 /home/sjc/.email_password
echo sjcsjc | sudo -S cp provisioning/notify-boot.service provisioning/telegram-bot.service /etc/systemd/system/
echo sjcsjc | sudo -S cp provisioning/10-noblank.conf /etc/X11/xorg.conf.d/ 2>/dev/null
echo sjcsjc | sudo -S systemctl daemon-reload
echo sjcsjc | sudo -S systemctl enable --now notify-boot.service telegram-bot.service

# --- 10. LED service ---
mkdir -p /home/sjc/dreammachine/led/venv
python3 -m venv /home/sjc/dreammachine/led/venv 2>/dev/null || true
/home/sjc/dreammachine/led/venv/bin/pip install -q python-osc spidev 2>/dev/null
echo sjcsjc | sudo -S cp "$GM/dreammachine-led.service" /etc/systemd/system/ 2>/dev/null || \
    echo sjcsjc | sudo -S cp /home/sjc/dreammachine/systemd/dreammachine-led.service /etc/systemd/system/
echo sjcsjc | sudo -S systemctl daemon-reload

# --- 11. SPI + DAC ---
echo sjcsjc | sudo -S raspi-config nonint do_spi 0
echo sjcsjc | sudo -S bash -c 'grep -q hifiberry /boot/firmware/config.txt || echo dtoverlay=hifiberry-dac >> /boot/firmware/config.txt'

# --- 12. Screen blanking ---
echo sjcsjc | sudo -S cp provisioning/10-noblank.conf /etc/X11/xorg.conf.d/ 2>/dev/null
echo sjcsjc | sudo -S bash -c 'grep -q consoleblank /boot/firmware/cmdline.txt || sed -i "s/ quiet splash/ quiet splash consoleblank=0/" /boot/firmware/cmdline.txt'

# --- 13. Autostart (must be executable!) ---
mkdir -p ~/.config/lxsession/rpd-x
cp "$GM/lxsession-autostart" ~/.config/lxsession/rpd-x/autostart 2>/dev/null || \
    echo "@/home/sjc/dreammachine/systemd/start_reaper.sh" >> ~/.config/lxsession/rpd-x/autostart
chmod +x ~/.config/lxsession/rpd-x/autostart
chmod +x /home/sjc/dreammachine/systemd/start_reaper.sh
chmod +x /home/sjc/dreammachine/rp2350/pattern.py
chmod +x /home/sjc/dreammachine/reaper/ensure_reaper_audio.sh
# Deploy display resolution fix for headless RustDesk
echo sjcsjc | sudo -S cp provisioning/set-display-resolution.desktop /etc/xdg/autostart/ 2>/dev/null || true
# Force HDMI hotplug for headless operation
echo sjcsjc | sudo -S bash -c 'grep -q "video=HDMI" /boot/firmware/cmdline.txt || sed -i "s/ quiet splash/ quiet splash video=HDMI-A-1:1920x1080@60e/" /boot/firmware/cmdline.txt' 2>/dev/null || true

# --- 14. POPO ---
if [ ! -d /home/sjc/popo/.git ]; then
    mkdir -p /home/sjc/popo
    git clone -q https://github.com/RVX/Popocatepetl_mounts-observatory_sonification.git /home/sjc/popo
fi
(crontab -l 2>/dev/null | grep -v popo; echo "7 * * * * cd /home/sjc/popo && /usr/bin/python3 POPO_fdsnws_mounts_omr.py --stagger-minutes $POPO_STAGGER >> /tmp/popo_live.log 2>&1") | crontab -
log "POPO cron: minute $(printf '%02d' $((7 + POPO_STAGGER))) (stagger ${POPO_STAGGER}min)"

# --- 15. Logrotate ---
echo sjcsjc | sudo -S cp provisioning/dreammachine-logrotate.sh /usr/local/bin/
echo sjcsjc | sudo -S chmod +x /usr/local/bin/dreammachine-logrotate.sh
echo "0 4 * * * /usr/local/bin/dreammachine-logrotate.sh" | echo sjcsjc | sudo -S tee /etc/cron.d/dreammachine-logrotate > /dev/null

# --- 16. RP2350 firmware ---
ELF="/home/sjc/dreammachine/rp2350/build/dreammachine_rp2350.elf"
if [ ! -f "$ELF" ] && [ -f /tmp/dreammachine_rp2350.elf ]; then
    mkdir -p "$(dirname "$ELF")"
    cp /tmp/dreammachine_rp2350.elf "$ELF"
fi
if [ -f "$ELF" ]; then
    log "Flashing RP2350..."
    echo sjcsjc | sudo -S openocd -f /home/sjc/dreammachine/rp2350/rpi4-rp2350-swd.cfg \
        -c 'transport select swd' -c 'source [find target/rp2350.cfg]' \
        -c "program $ELF verify reset exit" 2>&1 | grep -E "Verified|Error" || fail "RP2350 flash"
else
    fail "RP2350 .elf not found"
fi

# --- 17. Start LED service ---
echo sjcsjc | sudo -S systemctl enable --now dreammachine-led.service

# --- 18. Generate initial POPO wavs ---
log "Generating initial POPO sonifications..."
cd /home/sjc/popo && python3 POPO_fdsnws_mounts_omr.py --minutes 60 --delay-minutes 90 2>&1 | tail -1

# --- 19. Fix RPP references to local wavs ---
NEWEST=$(ls -t /home/sjc/popo/datasets/ground/sonifications/popo_live_*.wav 2>/dev/null | head -1)
if [ -n "$NEWEST" ]; then
    TS=$(basename "$NEWEST" | grep -oP 'popo_live_\K[0-9]+T[0-9]+_[0-9]+m')
    sed -i "s|popo_live_[^/\"]*_MX|popo_live_${TS}_MX|g" ~/reaper-projects/Dreammachine_popo_01/Dreammachine_popo_01.RPP
    log "RPP references updated to $TS"
fi

# --- 20. Send notification ---
python3 /home/sjc/notify.py 2>&1 | tail -1

# --- Summary ---
echo ""
log "=== $HOSTNAME provisioning complete ==="
log "Tailscale: $TS_IP"
log "RustDesk: $RD_ID (pwd: $RUSTDESK_PASSWORD)"
log "POPO: cron at :$(printf '%02d' $((7 + POPO_STAGGER)))"
if [ -n "$ERRORS" ]; then
    echo -e "\nWARNINGS:$ERRORS"
fi
log "Reboot to activate DAC overlay + full chain"
