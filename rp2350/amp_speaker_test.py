#!/usr/bin/env python3
import argparse
import math
import struct
import subprocess
import tempfile
import time
import wave
from pathlib import Path

import spidev


AMP_SHUTDOWN = 0x20
AMP_START_MUTED = 0x21
AMP_UNMUTE = 0x22
AMP_MUTE = 0x23


def send_command(command: int) -> None:
    with spidev.SpiDev() as spi:
        spi.open(0, 0)
        spi.max_speed_hz = 500_000
        spi.mode = 0
        spi.xfer2([command])


def write_tone(path: Path, channel: str, level_dbfs: int, duration: float) -> None:
    sample_rate = 48_000
    amplitude = int(32767 * (10 ** (level_dbfs / 20)))
    with wave.open(str(path), "wb") as output:
        output.setnchannels(2)
        output.setsampwidth(2)
        output.setframerate(sample_rate)
        for sample in range(int(sample_rate * duration)):
            value = int(amplitude * math.sin(2 * math.pi * 1000 * sample / sample_rate))
            frame = (value, 0) if channel == "left" else (0, value)
            output.writeframesraw(struct.pack("<hh", *frame))


def main() -> None:
    parser = argparse.ArgumentParser(description="Guarded TPA3118 speaker test")
    parser.add_argument("channel", choices=("left", "right"))
    parser.add_argument("--level", type=int, choices=(-50, -40), default=-50)
    parser.add_argument("--duration", type=float, default=2.0)
    parser.add_argument(
        "--scope",
        action="store_true",
        help="allow a longer no-load oscilloscope test (speaker must be disconnected)",
    )
    args = parser.parse_args()
    maximum_duration = 120.0 if args.scope else 3.0
    if not 0.5 <= args.duration <= maximum_duration:
        parser.error(f"duration must be between 0.5 and {maximum_duration:g} seconds")

    send_command(AMP_MUTE)
    send_command(AMP_SHUTDOWN)

    with tempfile.TemporaryDirectory() as directory:
        tone_path = Path(directory) / "speaker-test.wav"
        write_tone(tone_path, args.channel, args.level, args.duration)
        player = None
        try:
            send_command(AMP_START_MUTED)
            player = subprocess.Popen(
                ["aplay", "-D", "default", str(tone_path)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                text=True,
            )
            time.sleep(0.25)
            if player.poll() is not None:
                error = player.stderr.read().strip() if player.stderr else ""
                raise RuntimeError(f"aplay failed before unmute: {error}")
            send_command(AMP_UNMUTE)
            return_code = player.wait(timeout=args.duration + 2)
            if return_code != 0:
                error = player.stderr.read().strip() if player.stderr else ""
                raise RuntimeError(f"aplay exited {return_code}: {error}")
        finally:
            send_command(AMP_MUTE)
            send_command(AMP_SHUTDOWN)
            if player is not None and player.poll() is None:
                player.terminate()
                player.wait(timeout=2)

    print(
        f"Completed {args.channel} {'scope' if args.scope else 'speaker'} test "
        f"at {args.level} dBFS; "
        "amplifier is shut down"
    )


if __name__ == "__main__":
    main()