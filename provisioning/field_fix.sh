#!/bin/bash
# One-shot field fix: run this on dm1/dm3/dm4/dm5 (or re-run on dm2) to apply
# everything found/fixed during the 2026-09-30 reliability pass in one go.
# Safe to re-run; every step is idempotent.
#
#   ssh sjc@<unit> 'cd /home/sjc/dreammachine && git pull && bash provisioning/field_fix.sh'
set -e
cd /home/sjc/dreammachine

echo "==> [1/7] Executable bits on directly-exec'd autostart/systemd scripts"
# core.fileMode is set to false fleet-wide (stops false "modified" diffs from
# SD-card mount quirks), which means `git pull` silently never restores a lost
# +x bit. lxsession's `@`-prefixed autostart (start_reaper.sh) and bare
# ExecStart= paths (no `bash` prefix) exec() the file directly, so a missing
# +x fails completely silently -- no error anywhere. Re-assert on every run.
for f in systemd/start_reaper.sh; do
    if [ -f "$f" ] && [ ! -x "$f" ]; then
        chmod +x "$f"
        echo "    fixed missing +x -> $f"
    fi
done

echo "==> [2/7] Remove conflicting VNC stacks (RealVNC + wayvnc both bind :5900, wedges boot)"
sudo systemctl stop wayvnc-control.service wayvnc.service vncserver-x11-serviced.service 2>/dev/null || true
sudo systemctl disable wayvnc-control.service wayvnc.service vncserver-x11-serviced.service 2>/dev/null || true
sudo systemctl mask wayvnc-control.service wayvnc.service vncserver-x11-serviced.service vncserver-virtuald.service 2>/dev/null || true

echo "==> [3/7] Timezone"
if [ "$(timedatectl show -p Timezone --value)" != "America/Mexico_City" ]; then
    sudo timedatectl set-timezone America/Mexico_City
    echo "    fixed -> America/Mexico_City"
else
    echo "    already correct"
fi

echo "==> [4/7] Pin WiFi to the network currently in use (stop silent roaming)"
ACTIVE_WIFI=$(nmcli -t -f NAME,TYPE,DEVICE connection show --active | awk -F: '$2=="802-11-wireless"{print $1; exit}')
if [ -n "$ACTIVE_WIFI" ]; then
    sudo nmcli connection modify "$ACTIVE_WIFI" connection.autoconnect-priority 10
    while IFS=: read -r name type; do
        [ "$type" = "802-11-wireless" ] || continue
        [ "$name" = "$ACTIVE_WIFI" ] && continue
        sudo nmcli connection modify "$name" connection.autoconnect no
        echo "    disabled autoconnect on other profile: $name"
    done < <(nmcli -t -f NAME,TYPE connection show)
    echo "    pinned to: $ACTIVE_WIFI (priority 10)"
else
    echo "    WARNING: no active WiFi connection found, skipping"
fi

echo "==> [5/7] Reliability services (network/show watchdogs, show-hours gating, monitoring)"
bash provisioning/install_wifi_setup.sh
bash provisioning/install_show_hours.sh
bash provisioning/install_monitoring.sh

echo "==> [6/7] Health check"
echo "    REAPER:        $(pgrep -x reaper >/dev/null && echo running || echo NOT RUNNING)"
echo "    LED service:   $(systemctl is-active dreammachine-led.service)"
echo "    RustDesk ID:   $(sudo -n -u sjc rustdesk --get-id 2>/dev/null || echo unknown)"
echo "    Local IP:      $(hostname -I | awk '{print $1}')"
echo "    Telegram bot:  $(systemctl is-active telegram-bot.service 2>/dev/null) (must be inactive unless this is sjcdm4)"
echo "    VNC (:5900):   $(sudo ss -tlnp 2>/dev/null | grep -q 5900 && echo 'STILL LISTENING - FIX NEEDED' || echo clear)"

echo "==> [7/7] Done. Timers:"
systemctl list-timers 'dreammachine-*' --no-pager
