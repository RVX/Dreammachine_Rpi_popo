#!/bin/bash
# Debug + fix REAPER autostart on this unit
echo "=== lxsession started ==="
LXPID=$(pgrep -f lxsession | head -1)
ps -o lstart= -p "$LXPID" 2>/dev/null || echo "no lxsession"

echo "=== autostart file created ==="
stat -c '%y' /home/sjc/.config/lxsession/rpd-x/autostart

echo "=== reaper running? ==="
pgrep -x reaper && echo YES || echo NO

echo "=== start_reaper.log ==="
cat /tmp/start_reaper.log 2>/dev/null || echo "no log (script never ran)"

echo "=== fixing: restart desktop session ==="
echo sjcsjc | sudo -S systemctl restart lightdm
