#!/usr/bin/env python3
"""amp_test.py — verify amp power and mute status via RP2350."""
import spidev
import sys

CMDS = {
    "shutdown": 0x20,
    "start": 0x21,
    "unmute": 0x22,
    "mute": 0x23,
}

spi = spidev.SpiDev()
spi.open(0, 0)
spi.max_speed_hz = 500_000

for name, cmd in [("start", 0x21), ("unmute", 0x22)]:
    spi.xfer2([cmd])
    print(f"sent-{name}-0x{cmd:02x}")

spi.close()
