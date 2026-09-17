#!/usr/bin/env python3
import argparse
import time

import spidev


COMMANDS = {
    "off": 0x00,
    "chase": 0x10,
    "bounce": 0x11,
    "flash": 0x12,
    "amp-shutdown": 0x20,
    "amp-start-muted": 0x21,
    "amp-unmute": 0x22,
    "amp-mute": 0x23,
}


def main() -> None:
    parser = argparse.ArgumentParser(description="Control DREAMMACHINE RP2350B LED patterns")
    parser.add_argument("pattern", choices=(*COMMANDS, "pulse"))
    parser.add_argument("channel", type=int, nargs="?", choices=range(1, 7))
    args = parser.parse_args()

    if args.pattern == "pulse" and args.channel is None:
        parser.error("pulse requires a channel from 1 to 6")
    if args.pattern != "pulse" and args.channel is not None:
        parser.error("channel is only valid with pulse")

    command = args.channel if args.pattern == "pulse" else COMMANDS[args.pattern]
    with spidev.SpiDev() as spi:
        spi.open(0, 0)
        spi.max_speed_hz = 500_000
        spi.mode = 0
        spi.xfer2([command])

    print(f"Sent {args.pattern} command 0x{command:02x}")
    if args.pattern != "off":
        time.sleep(0.1)


if __name__ == "__main__":
    main()