#!/bin/bash
# One-shot field fix: run this on dm1/dm3/dm4/dm5 (or re-run on dm2) to apply
# everything found/fixed during the 2026-09-30 reliability pass in one go.
# Safe to re-run; every step is idempotent.
#
#   ssh sjc@<unit> 'cd /home/sjc/dreammachine && git pull && bash provisioning/field_fix.sh'
set -e
cd /home/sjc/dreammachine

echo "==> [1/6] Executable bits on directly-exec'd autostart/systemd scripts"
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

echo "==> [2/6] Timezone"
if [ "$(timedatectl show -p Timezone --value)" != "America/Mexico_City" ]; then
    sudo timedatectl set-timezone America/Mexico_City
    echo "    fixed -> America/Mexico_City"
else
    echo "    already correct"
fi

echo "==> [3/6] Pin WiFi to the network currently in use (stop silent roaming)"
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

echo "==> [4/6] Reliability services (network/show watchdogs, show-hours gating, monitoring)"
bash provisioning/install_wifi_setup.sh
bash provisioning/install_show_hours.sh
bash provisioning/install_monitoring.sh

echo "==> [5/6] Health check"
echo "    REAPER:      $(pgrep -x reaper >/dev/null && echo running || echo NOT RUNNING)"
echo "    LED service: $(systemctl is-active dreammachine-led.service)"
echo "    RustDesk ID: $(sudo -n -u sjc rustdesk --get-id 2>/dev/null || echo unknown)"
echo "    Local IP:    $(hostname -I | awk '{print $1}')"

echo "==> [6/6] Done. Timers:"
systemctl list-timers 'dreammachine-*' --no-pager
