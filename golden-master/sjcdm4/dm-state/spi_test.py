#!/usr/bin/env python3
"""spi_test.py — send raw SPI bytes to RP2350 for hardware verification."""
import spidev
import sys
import time

CMDS = {
    "on": 0x08,
    "off": 0x09,
    "pulse": 0x07,
    "alloff": 0x00,
}

action = sys.argv[1] if len(sys.argv) > 1 else "pulse"

spi = spidev.SpiDev()
spi.open(0, 0)
spi.max_speed_hz = 500_000

if action == "strobe":
    # 5 Hz for 2 seconds to verify timing
    for i in range(10):
        spi.xfer2([0x08])
        time.sleep(0.1)
        spi.xfer2([0x09])
        time.sleep(0.1)
    print("strobe-test-done")
elif action in CMDS:
    spi.xfer2([CMDS[action]])
    print(f"sent-{action}-0x{CMDS[action]:02x}")
else:
    print(f"unknown: {action}")

spi.close()
