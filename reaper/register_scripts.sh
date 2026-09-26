#!/bin/bash
# Register DM scripts in REAPER's action list
KB=/home/sjc/.config/REAPER/reaper-kb.ini

H1=$(echo -n "DM_Autoloop_Tracks_1-4.lua" | md5sum | awk '{print $1}')
H2=$(echo -n "DM_Sonifications_Tracks_5-10.lua" | md5sum | awk '{print $1}')

# Remove any previous bad entries
sed -i '/DM_Autoloop\|DM_Sonifications/d' "$KB"

# Add proper entries
echo "SCR 4 0 RS${H1} \"Custom: DM_Autoloop_Tracks_1-4.lua\" \"DM_Autoloop_Tracks_1-4.lua\"" >> "$KB"
echo "SCR 4 0 RS${H2} \"Custom: DM_Sonifications_Tracks_5-10.lua\" \"DM_Sonifications_Tracks_5-10.lua\"" >> "$KB"

echo "Registered:"
grep "DM_" "$KB"
echo ""
echo "Action IDs:"
echo "  _RS${H1}"
echo "  _RS${H2}"
