#!/bin/bash
GM=/home/sjc/dreammachine/golden-master/sjcdm4/dm-state
mkdir -p /home/sjc/reaper-projects/Dreammachine_popo_01 /home/sjc/.config/REAPER/Scripts /home/sjc/.config/REAPER/UserPlugins

cp "$GM/Dreammachine_popo_01.RPP" /home/sjc/reaper-projects/Dreammachine_popo_01/ && echo RPP-OK
cp "$GM/reaper.ini" "$GM/reaper-kb.ini" /home/sjc/.config/REAPER/ && echo INI-OK
cp "$GM/Scripts/DM_Autoloop_Tracks_1-4.lua" "$GM/Scripts/DM_Sonifications_Tracks_5-10.lua" "$GM/Scripts/__startup.lua" /home/sjc/.config/REAPER/Scripts/ && echo SCRIPTS-OK

# Notifications
cd /home/sjc/dreammachine
cp provisioning/notify.py provisioning/notify_boot.sh provisioning/dm_update.sh /home/sjc/
chmod +x /home/sjc/notify.py /home/sjc/notify_boot.sh /home/sjc/dm_update.sh
echo -n "sxiterhlujuyrbtm" > /home/sjc/.email_password
chmod 600 /home/sjc/.email_password
echo sjcsjc | sudo -S cp provisioning/notify-boot.service /etc/systemd/system/
echo sjcsjc | sudo -S systemctl daemon-reload
echo sjcsjc | sudo -S systemctl enable --now notify-boot.service
# sjcdm3 is not the fleet master — telegram_bot.py must stay disabled here,
# it would 409-conflict with telegram_bot_master.py polling on sjcdm4.
echo sjcsjc | sudo -S systemctl disable --now telegram-bot.service 2>/dev/null

# LED service
mkdir -p /home/sjc/dreammachine/led/venv
python3 -m venv /home/sjc/dreammachine/led/venv 2>/dev/null
/home/sjc/dreammachine/led/venv/bin/pip install -q python-osc spidev 2>/dev/null
echo sjcsjc | sudo -S cp "$GM/dreammachine-led.service" /etc/systemd/system/ 2>/dev/null || echo sjcsjc | sudo -S cp /home/sjc/dreammachine/systemd/dreammachine-led.service /etc/systemd/system/
echo sjcsjc | sudo -S systemctl daemon-reload
echo sjcsjc | sudo -S systemctl enable --now dreammachine-led.service

# SPI + DAC
echo sjcsjc | sudo -S raspi-config nonint do_spi 0
echo sjcsjc | sudo -S bash -c 'grep -q hifiberry /boot/firmware/config.txt || echo dtoverlay=hifiberry-dac >> /boot/firmware/config.txt'

# Screen blanking
echo sjcsjc | sudo -S cp provisioning/10-noblank.conf /etc/X11/xorg.conf.d/ 2>/dev/null
echo sjcsjc | sudo -S bash -c 'grep -q consoleblank /boot/firmware/cmdline.txt || sed -i "s/ quiet splash/ quiet splash consoleblank=0/" /boot/firmware/cmdline.txt'

# Autostart
mkdir -p /home/sjc/.config/lxsession/rpd-x
cp "$GM/lxsession-autostart" /home/sjc/.config/lxsession/rpd-x/autostart 2>/dev/null
chmod +x /home/sjc/.config/lxsession/rpd-x/autostart
chmod +x /home/sjc/dreammachine/systemd/start_reaper.sh /home/sjc/dreammachine/rp2350/pattern.py /home/sjc/dreammachine/reaper/ensure_reaper_audio.sh

# POPO
if [ ! -d /home/sjc/popo/.git ]; then
    mkdir -p /home/sjc/popo
    git clone -q https://github.com/RVX/Popocatepetl_mounts-observatory_sonification.git /home/sjc/popo
fi
(crontab -l 2>/dev/null | grep -v popo; echo "7 * * * * cd /home/sjc/popo && /usr/bin/python3 POPO_fdsnws_mounts_omr.py --stagger-minutes 30 >> /tmp/popo_live.log 2>&1") | crontab -

# Logrotate
echo sjcsjc | sudo -S cp provisioning/dreammachine-logrotate.sh /usr/local/bin/
echo sjcsjc | sudo -S chmod +x /usr/local/bin/dreammachine-logrotate.sh
echo "0 4 * * * /usr/local/bin/dreammachine-logrotate.sh" | echo sjcsjc | sudo -S tee /etc/cron.d/dreammachine-logrotate > /dev/null

# RP2350 flash
echo sjcsjc | sudo -S openocd -f /home/sjc/dreammachine/rp2350/rpi4-rp2350-swd.cfg \
    -c 'transport select swd' -c 'source [find target/rp2350.cfg]' \
    -c 'program /home/sjc/dreammachine/rp2350/build/dreammachine_rp2350.elf verify reset exit' 2>&1 | grep -E "Verified|Error"

# Copy firmware .elf if missing (it's gitignored)
if [ ! -f /home/sjc/dreammachine/rp2350/build/dreammachine_rp2350.elf ]; then
    mkdir -p /home/sjc/dreammachine/rp2350/build
    echo "NOTE: RP2350 .elf not in repo (gitignored) — flash skipped"
fi

# Initial POPO
cd /home/sjc/popo && python3 POPO_fdsnws_mounts_omr.py --minutes 60 --delay-minutes 90 2>&1 | tail -1

# Notify
python3 /home/sjc/notify.py 2>&1 | tail -1

echo "=== sjcdm3 provisioning complete ==="
