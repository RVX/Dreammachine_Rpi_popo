#!/bin/bash
# provision_unit.sh — One-shot DREAMMACHINE unit provisioning.
# Run on a fresh Pi via SSH after SSH keys are set up:
#   ssh sjc@<ip> 'bash -s' < provision_unit.sh
#
# Does everything: hostname, Tailscale, repo, REAPER, extensions,
# notifications, POPO, RP2350 flash, LED service, autostart, logrotate.
# Idempotent — safe to run multiple times.

set -e
UNIT_NUM="$1"  # e.g. 2, 3, 5
HOSTNAME="sjcdm${UNIT_NUM}"
POPO_STAGGER=$((UNIT_NUM * 10))
REPO="https://github.com/RVX/Dreammachine_Rpi_popo.git"
TAILSCALE_KEY="tskey-auth-krgtTx2qEZ11CNTRL-FSuzLc4JU3GL7TdpEx3N3GwLfhjXzNBZ"
EMAIL_PASSWORD="sxiterhlujuyrbtm"
SSH_KEY="ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIHtzs5WjIRKy5zZnc0z1GGvKBjFVIf1vCukw6QWqtX9G dreammachine-pi"

log() { echo "[$(date '+%H:%M:%S')] $1"; }

# --- 1. Hostname + SSH key ---
log "Setting hostname to $HOSTNAME..."
echo sjcsjc | sudo -S hostnamectl set-hostname "$HOSTNAME" 2>/dev/null
echo sjcsjc | sudo -S sed -i "s/127.0.1.1.*/127.0.1.1\t$HOSTNAME/" /etc/hosts 2>/dev/null
mkdir -p ~/.ssh
grep -q "dreammachine-pi" ~/.ssh/authorized_keys 2>/dev/null || echo "$SSH_KEY" >> ~/.ssh/authorized_keys
chmod 700 ~/.ssh; chmod 600 ~/.ssh/authorized_keys
echo sjcsjc | sudo -S systemctl enable ssh 2>/dev/null

# --- 2. Tailscale ---
if ! tailscale ip -4 >/dev/null 2>&1; then
    log "Installing Tailscale..."
    curl -fsSL https://tailscale.com/install.sh | sh 2>&1 | tail -1
    echo sjcsjc | sudo -S tailscale up --authkey="$TAILSCALE_KEY" --hostname="$HOSTNAME" --accept-routes
fi
TS_IP=$(tailscale ip -4 2>/dev/null || echo "pending")
log "Tailscale: $TS_IP"

# --- 3. Repo ---
if [ ! -d /home/sjc/dreammachine/.git ]; then
    log "Cloning repo..."
    mkdir -p /home/sjc/dreammachine
    git clone -q "$REPO" /home/sjc/dreammachine
fi
cd /home/sjc/dreammachine && git pull --ff-only -q 2>/dev/null || true

# --- 4. System packages ---
log "Installing packages..."
echo sjcsjc | sudo -S apt install -y -qq openocd python3-pip python3-venv curl figlet avahi-daemon 2>&1 | tail -1
pip3 install --user --break-system-packages -q obspy python-osc spidev 2>&1 | tail -1

# --- 5. REAPER ---
if [ ! -f /opt/REAPER/REAPER/reaper ]; then
    log "Installing REAPER..."
    # Try downloading from reaper.fm (may need local scp fallback)
    if curl -fsSL -A "Mozilla/5.0" -o /tmp/reaper.tar.xz "https://www.reaper.fm/files/7.x/reaper780_linux_aarch64.tar.xz" 2>/dev/null; then
        echo sjcsjc | sudo -S tar xf /tmp/reaper.tar.xz -C /opt/
        echo sjcsjc | sudo -S ln -sf /opt/REAPER/REAPER/reaper /usr/local/bin/reaper
    else
        log "WARN: REAPER download failed (403) — copy manually or scp from another unit"
    fi
fi
echo sjcsjc | sudo -S ln -sf /opt/REAPER/REAPER/reaper /usr/local/bin/reaper 2>/dev/null || true

# --- 6. REAPER extensions ---
mkdir -p ~/.config/REAPER/UserPlugins ~/.config/REAPER/Scripts
for ext in reaper_sws-aarch64.so reaper_reapack-aarch64.so; do
    if [ ! -f ~/.config/REAPER/UserPlugins/$ext ]; then
        if [ -f /tmp/$ext ]; then
            cp /tmp/$ext ~/.config/REAPER/UserPlugins/
        else
            log "WARN: $ext not in /tmp — copy from another unit or download"
        fi
    fi
done

# --- 7. REAPER project + config from golden master ---
mkdir -p ~/reaper-projects/Dreammachine_popo_01
GM="/home/sjc/dreammachine/golden-master/sjcdm4/dm-state"
if [ -d "$GM" ]; then
    cp "$GM/Dreammachine_popo_01.RPP" ~/reaper-projects/Dreammachine_popo_01/ 2>/dev/null
    cp "$GM/reaper.ini" ~/.config/REAPER/ 2>/dev/null
    cp "$GM/reaper-kb.ini" ~/.config/REAPER/ 2>/dev/null
    cp "$GM/Scripts/DM_"* ~/.config/REAPER/Scripts/ 2>/dev/null
    cp "$GM/Scripts/__startup.lua" ~/.config/REAPER/Scripts/ 2>/dev/null
fi

# --- 8. Notifications ---
cp provisioning/notify.py provisioning/telegram_bot.py provisioning/notify_boot.sh provisioning/dm_update.sh /home/sjc/
chmod +x /home/sjc/notify.py /home/sjc/telegram_bot.py /home/sjc/notify_boot.sh /home/sjc/dm_update.sh
echo -n "$EMAIL_PASSWORD" > /home/sjc/.email_password
chmod 600 /home/sjc/.email_password
echo sjcsjc | sudo -S cp provisioning/notify-boot.service provisioning/telegram-bot.service /etc/systemd/system/
echo sjcsjc | sudo -S cp provisioning/10-noblank.conf /etc/X11/xorg.conf.d/ 2>/dev/null

# --- 9. Services ---
echo sjcsjc | sudo -S systemctl daemon-reload
echo sjcsjc | sudo -S systemctl enable notify-boot.service telegram-bot.service
echo sjcsjc | sudo -S systemctl start telegram-bot.service

# --- 10. LED service ---
mkdir -p /home/sjc/dreammachine/led/venv
python3 -m venv /home/sjc/dreammachine/led/venv 2>/dev/null || true
/home/sjc/dreammachine/led/venv/bin/pip install -q python-osc spidev 2>/dev/null
echo sjcsjc | sudo -S cp "$GM/dreammachine-led.service" /etc/systemd/system/ 2>/dev/null || \
    echo sjcsjc | sudo -S cp /home/sjc/dreammachine/systemd/dreammachine-led.service /etc/systemd/system/
echo sjcsjc | sudo -S systemctl daemon-reload
echo sjcsjc | sudo -S systemctl enable --now dreammachine-led.service

# --- 11. SPI + DAC ---
echo sjcsjc | sudo -S raspi-config nonint do_spi 0
echo sjcsjc | sudo -S bash -c 'grep -q hifiberry /boot/firmware/config.txt || echo dtoverlay=hifiberry-dac >> /boot/firmware/config.txt'

# --- 12. Screen blanking ---
echo sjcsjc | sudo -S cp provisioning/10-noblank.conf /etc/X11/xorg.conf.d/ 2>/dev/null
echo sjcsjc | sudo -S bash -c 'grep -q consoleblank /boot/firmware/cmdline.txt || sed -i "s/ quiet splash/ quiet splash consoleblank=0/" /boot/firmware/cmdline.txt'

# --- 13. Autostart ---
mkdir -p ~/.config/lxsession/rpd-x
cp "$GM/lxsession-autostart" ~/.config/lxsession/rpd-x/autostart 2>/dev/null || \
    echo "@/home/sjc/dreammachine/systemd/start_reaper.sh" >> ~/.config/lxsession/rpd-x/autostart
chmod +x ~/.config/lxsession/rpd-x/autostart
chmod +x /home/sjc/dreammachine/systemd/start_reaper.sh
chmod +x /home/sjc/dreammachine/rp2350/pattern.py
chmod +x /home/sjc/dreammachine/reaper/ensure_reaper_audio.sh

# --- 14. POPO ---
if [ ! -d /home/sjc/popo/.git ]; then
    mkdir -p /home/sjc/popo
    git clone -q https://github.com/RVX/Popocatepetl_mounts-observatory_sonification.git /home/sjc/popo
fi
(crontab -l 2>/dev/null | grep -v popo; echo "7 * * * * cd /home/sjc/popo && /usr/bin/python3 POPO_fdsnws_mounts_omr.py --stagger-minutes $POPO_STAGGER >> /tmp/popo_live.log 2>&1") | crontab -

# --- 15. Logrotate ---
echo sjcsjc | sudo -S cp provisioning/dreammachine-logrotate.sh /usr/local/bin/
echo sjcsjc | sudo -S chmod +x /usr/local/bin/dreammachine-logrotate.sh
echo "0 4 * * * /usr/local/bin/dreammachine-logrotate.sh" | echo sjcsjc | sudo -S tee /etc/cron.d/dreammachine-logrotate > /dev/null

# --- 16. RP2350 firmware ---
if [ -f /home/sjc/dreammachine/rp2350/build/dreammachine_rp2350.elf ]; then
    log "Flashing RP2350..."
    echo sjcsjc | sudo -S openocd -f /home/sjc/dreammachine/rp2350/rpi4-rp2350-swd.cfg \
        -c 'transport select swd' -c 'source [find target/rp2350.cfg]' \
        -c 'program /home/sjc/dreammachine/rp2350/build/dreammachine_rp2350.elf verify reset exit' 2>&1 | grep -E "Verified|Error"
else
    log "WARN: RP2350 firmware not found — copy .elf from another unit"
fi

# --- 17. Generate initial POPO wavs ---
log "Generating initial POPO sonifications..."
cd /home/sjc/popo && python3 POPO_fdsnws_mounts_omr.py --minutes 60 --delay-minutes 90 2>&1 | tail -1

# --- 18. Send notification ---
python3 /home/sjc/notify.py 2>&1 | tail -1

log "=== $HOSTNAME provisioning complete ==="
log "Tailscale: $TS_IP"
log "POPO stagger: ${POPO_STAGGER}min (cron at :$(printf '%02d' $((7 + POPO_STAGGER))))"
log "Reboot to activate DAC overlay + full chain"
