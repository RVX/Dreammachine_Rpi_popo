#!/bin/bash
# Disable console blanking in kernel cmdline (one-time)
CMDLINE=/boot/firmware/cmdline.txt
if ! grep -q "consoleblank=0" "$CMDLINE"; then
    sed -i 's/ quiet splash/ quiet splash consoleblank=0/' "$CMDLINE"
    echo "consoleblank=0 added to $CMDLINE"
else
    echo "consoleblank=0 already present"
fi
grep -o "consoleblank=0" "$CMDLINE"
