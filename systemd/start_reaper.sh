#!/usr/bin/env bash
# Launches REAPER after a short delay to let the desktop/audio stack settle.
# Used as an lxsession (rpd-x/X11) autostart entry.
sleep 8
exec /usr/local/bin/reaper "/home/sjc/reaper-projects/Dreammachine_popo_01/Dreammachine_popo_01.RPP"
