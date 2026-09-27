#!/bin/bash
# Fix RPP: replace ALL popo_live references with the newest timestamp
RPP=/home/sjc/reaper-projects/Dreammachine_popo_01/Dreammachine_popo_01.RPP
NEWEST=$(ls -t /home/sjc/popo/datasets/ground/sonifications/popo_live_*.wav 2>/dev/null | head -1)
if [ -z "$NEWEST" ]; then
    echo "No POPO wavs found"
    exit 1
fi
TS=$(basename "$NEWEST" | grep -oP 'popo_live_\K[0-9]+T[0-9]+_[0-9]+m')
echo "Newest: $TS"
# Replace any popo_live_*_MX pattern (with or without existing timestamp) with the correct one
sed -i "s|popo_live_[^/\"]*_MX|popo_live_${TS}_MX|g" "$RPP"
echo "References updated:"
grep -c "popo_live_${TS}" "$RPP"
