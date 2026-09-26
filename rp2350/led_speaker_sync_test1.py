#!/usr/bin/env python3
"""
LED_SPEAKER_SYNC_TEST1 — sight+sound sync test for AMOS1 (GPIO33) and AMOS2 (GPIO34).

Maps audio frequencies to LED pulse repetition frequency on two channels:
  - AMOS1 follows a 20-200 Hz bass sweep; low freq = slow pulse, high = fast.
  - AMOS2 follows a 200 Hz-2 kHz sweep (band-separated companion).
  - Then a 2 Hz kick-sync segment: both channels flash exactly on each kick hit.

Audio plays through the PCM5102A DAC (hw:2,0) + TPA3118 amp (left mono).
LED channels are driven by RP2350B firmware over SPI0 (pulse commands 0x01/0x02).

NOTE: firmware pulses are fixed 500 ms on/off per command, so "brightness"
modulation here is via pulse RATE, not PWM duty cycle. True PWM brightness
control needs a firmware extension (see rp2350/main.c TODO).

Usage (on the Pi):
  python3 rp2350/led_speaker_sync_test1.py            # full test
  python3 rp2350/led_speaker_sync_test1.py --dry-run  # no audio, LEDs only
"""
import argparse
import subprocess
import threading
import time

import spidev

SPI_BUS = 0
SPI_CS = 0
SPI_SPEED = 500_000

CMD_ALL_OFF = 0x00
CMD_AMOS1_PULSE = 0x01   # GPIO33
CMD_AMOS2_PULSE = 0x02   # GPIO34
CMD_AMP_SHUTDOWN = 0x20
CMD_AMP_START_MUTED = 0x21
CMD_AMP_UNMUTE = 0x22

PULSE_LEN_S = 0.5  # legacy firmware pulse() duration (pattern commands)

# Non-blocking fade commands (firmware runs fade locally on RP2350):
def fade_in_cmd(channel):
    return 0x50 | channel  # 0x51-0x56 = fade in ch1-6 over ~1s


def fade_out_cmd(channel):
    return 0x60 | channel  # 0x61-0x66 = fade out ch1-6 over ~1s


def open_spi():
    spi = spidev.SpiDev()
    spi.open(SPI_BUS, SPI_CS)
    spi.max_speed_hz = SPI_SPEED
    spi.mode = 0
    return spi


def send(spi, cmd):
    spi.xfer2([cmd])


def fade_in(spi, channel):
    """Start non-blocking fade-in on channel (runs on RP2350)."""
    send(spi, fade_in_cmd(channel))


def fade_out(spi, channel):
    """Start non-blocking fade-out on channel (runs on RP2350)."""
    send(spi, fade_out_cmd(channel))


def play_sweep(f_start, f_end, duration_s, volume=0.5):
    """Generate a log sine sweep on the fly with ffmpeg and play on hw:2,0."""
    expr = f"sin(2*PI*{f_start}*pow({f_end/f_start},t/{duration_s})*t)"
    cmd = [
        "ffmpeg", "-loglevel", "error", "-f", "lavfi",
        "-i", f"sine=frequency={f_start}:duration={duration_s}",
        "-af", f"volume={volume}",
        "-f", "wav", "-acodec", "pcm_s32le", "-ar", "48000", "-ac", "2",
        "/tmp/sync_sweep.wav", "-y",
    ]
    subprocess.run(cmd, check=True)
    return subprocess.Popen(["aplay", "-D", "hw:2,0", "-q", "/tmp/sync_sweep.wav"])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true",
                        help="LEDs only, no audio/amp")
    args = parser.parse_args()

    spi = open_spi()
    stop = threading.Event()
    audio_proc = None

    try:
        print("=== LED_SPEAKER_SYNC_TEST1 ===")
        print("Stage 0: amp start-muted")
        send(spi, CMD_AMP_START_MUTED)
        time.sleep(0.3)

        if not args.dry_run:
            send(spi, CMD_AMP_UNMUTE)
            print("Amp unmuted (only latches if FAULTZ high)")

        # --- Stage 1: AMOS1 fade IN with 100 Hz tone ---
        print("Stage 1: AMOS1 (GPIO33) fading IN with 100 Hz tone, 2 s")
        if not args.dry_run:
            audio_proc = play_sweep(100, 100, 2, volume=0.4)  # steady 100 Hz
        fade_in(spi, 1)
        if audio_proc:
            audio_proc.wait()
        time.sleep(1.5)  # let fade complete

        # --- Stage 2: AMOS1 fade OUT with 200 Hz tone ---
        print("Stage 2: AMOS1 (GPIO33) fading OUT with 200 Hz tone, 2 s")
        if not args.dry_run:
            audio_proc = play_sweep(200, 200, 2, volume=0.4)
        fade_out(spi, 1)
        if audio_proc:
            audio_proc.wait()
        time.sleep(1.5)

        # --- Stage 3: AMOS2 fade IN with 400 Hz tone ---
        print("Stage 3: AMOS2 (GPIO34) fading IN with 400 Hz tone, 2 s")
        if not args.dry_run:
            audio_proc = play_sweep(400, 400, 2, volume=0.35)
        fade_in(spi, 2)
        if audio_proc:
            audio_proc.wait()
        time.sleep(1.5)

        # --- Stage 4: AMOS2 fade OUT with 800 Hz tone ---
        print("Stage 4: AMOS2 (GPIO34) fading OUT with 800 Hz tone, 2 s")
        if not args.dry_run:
            audio_proc = play_sweep(800, 800, 2, volume=0.35)
        fade_out(spi, 2)
        if audio_proc:
            audio_proc.wait()
        time.sleep(1.5)

        # --- Stage 5: kick-sync, both channels pulse on each hit ---
        print("Stage 5: kick-sync — both channels flash on each kick, 10 hits")
        if not args.dry_run:
            subprocess.run([
                "ffmpeg", "-loglevel", "error", "-f", "lavfi",
                "-i", "sine=frequency=60:duration=0.25",
                "-af", "volume=0.6,afade=t=out:st=0.05:d=0.2",
                "-f", "wav", "-acodec", "pcm_s32le", "-ar", "48000", "-ac", "2",
                "/tmp/sync_kick.wav", "-y",
            ], check=True)
        for i in range(10):
            # Dual pulse: both channels flash together for 100ms (firmware 0x07)
            send(spi, 0x07)
            if not args.dry_run:
                audio_proc = subprocess.Popen(
                    ["aplay", "-D", "hw:2,0", "-q", "/tmp/sync_kick.wav"])
                audio_proc.wait()
            print(f"  hit {i + 1}/10")
            time.sleep(0.5)

        print("=== TEST COMPLETE ===")

    finally:
        stop.set()
        if audio_proc and audio_proc.poll() is None:
            audio_proc.terminate()
        send(spi, CMD_ALL_OFF)  # all MOSFETs off + amp shutdown
        spi.close()
        print("All outputs off, amp shut down.")


if __name__ == "__main__":
    main()
