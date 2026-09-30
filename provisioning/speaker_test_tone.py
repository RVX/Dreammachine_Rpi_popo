#!/usr/bin/env python3
"""speaker_test_tone.py — generate long high-pitch test tones for speaker verification.
Usage: speaker_test_tone.py [tone|sweep|pulse|off]
"""
import sys
import time
import spidev

CMDS = {
    "on": 0x08,
    "off": 0x09,
    "pulse": 0x07,
    "alloff": 0x00,
}

spi = spidev.SpiDev()
spi.open(0, 0)
spi.max_speed_hz = 500_000

action = sys.argv[1] if len(sys.argv) > 1 else "tone"

if action == "tone":
    # 2 kHz tone for 5 seconds (high pitch, clearly audible)
    print("Playing 2 kHz tone for 5 seconds...")
    freq = 2000
    period = 1.0 / freq
    end_time = time.monotonic() + 5.0
    while time.monotonic() < end_time:
        spi.xfer2([CMDS["on"]])
        time.sleep(period / 2)
        spi.xfer2([CMDS["off"]])
        time.sleep(period / 2)
    print("tone-done")

elif action == "sweep":
    # Sweep 500 Hz to 4 kHz over 10 seconds
    print("Playing 500Hz-4kHz sweep for 10 seconds...")
    start_time = time.monotonic()
    duration = 10.0
    while time.monotonic() - start_time < duration:
        elapsed = time.monotonic() - start_time
        freq = 500 + (3500 * elapsed / duration)
        period = 1.0 / freq
        spi.xfer2([CMDS["on"]])
        time.sleep(period / 2)
        spi.xfer2([CMDS["off"]])
        time.sleep(period / 2)
    print("sweep-done")

elif action == "pulse":
    # Long 100 Hz pulses, 10x, clearly visible/hearable
    print("Playing 100 Hz pulse train (10 pulses)...")
    for i in range(10):
        print(f"  pulse {i+1}/10")
        spi.xfer2([CMDS["on"]])
        time.sleep(0.5)
        spi.xfer2([CMDS["off"]])
        time.sleep(0.5)
    print("pulse-done")

elif action == "off":
    spi.xfer2([CMDS["alloff"]])
    print("all-off")

else:
    print(f"unknown: {action}")
    print("Usage: speaker_test_tone.py [tone|sweep|pulse|off]")

spi.close()
