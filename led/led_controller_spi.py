#!/usr/bin/env python3
"""
led_controller_spi.py — DREAMMACHINE LED controller (RP2350 SPI), FLS-only.

Drives the 6 MOSFET LED channels through the RP2350B coprocessor over SPI0.
The 60-minute FLS stroboscopic research protocol is the only mode: it starts
automatically on launch and runs permanently in a loop until the process is
stopped (systemd stop/reboot). There is no OSC/remote override — REAPER does
not drive this script in the expo deployment, and FLS cannot be paused or
reverted to the old ambient/test patterns at runtime.

The RP2350 firmware owns all PWM timing — this script only sends single-byte
commands, which are non-blocking on the firmware side.

Command set (must match rp2350/main.c):
  0x00        all off + amp shutdown
  0x08/0x09   AMOS1+2 held ON/OFF (non-blocking, FLS strobe)
  0x51-0x56   fade IN ch1-6 (non-blocking, ~1 s)
  0x61-0x66   fade OUT ch1-6
  0x71-0x76   stop fade ch1-6

Config: config/dreammachine.env (LED channels count).

Restart policy: runs under systemd (dreammachine-led.service, Restart=always).
SIGTERM handler ensures cleanup path (all off) runs on stop/reboot.
"""
import signal
import threading
import time
from pathlib import Path

import spidev

# ---------------------------------------------------------------- config ---

REPO_ROOT = Path(__file__).resolve().parent.parent
ENV_PATH = REPO_ROOT / "config" / "dreammachine.env"


def load_env(path: Path) -> dict:
    values = {}
    if not path.exists():
        return values
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        values[key.strip()] = val.strip()
    return values


ENV = load_env(ENV_PATH)

NUM_CHANNELS = int(ENV.get("LED_NUM_CHANNELS", "6"))

SPI_BUS = 0
SPI_CS = 0
SPI_SPEED = 500_000

# Firmware commands
CMD_ALL_OFF = 0x00
CMD_DUAL_ON = 0x08           # AMOS1+2 held ON  (non-blocking, FLS strobe)
CMD_DUAL_OFF = 0x09          # AMOS1+2 OFF      (non-blocking, FLS strobe)
CMD_FADE_IN_BASE = 0x50      # | channel (1-6)
CMD_FADE_OUT_BASE = 0x60     # | channel
CMD_STOP_FADE_BASE = 0x70    # | channel

# Timing
FADE_DURATION_S = 1.0      # firmware fade time (~1 s)

# ------------------------------------------------------------------ SPI ----

class RP2350:
    def __init__(self):
        self.spi = spidev.SpiDev()
        self.spi.open(SPI_BUS, SPI_CS)
        self.spi.max_speed_hz = SPI_SPEED
        self.spi.mode = 0
        self._lock = threading.Lock()

    def send(self, cmd: int):
        with self._lock:
            self.spi.xfer2([cmd & 0xFF])

    def fade_in(self, ch: int):
        self.send(CMD_FADE_IN_BASE | ch)

    def fade_out(self, ch: int):
        self.send(CMD_FADE_OUT_BASE | ch)

    def stop_fade(self, ch: int):
        self.send(CMD_STOP_FADE_BASE | ch)

    def all_off(self):
        for ch in range(1, NUM_CHANNELS + 1):
            self.send(CMD_STOP_FADE_BASE | ch)
        # re-assert PWM low on every channel via fade-out then stop
        for ch in range(1, NUM_CHANNELS + 1):
            self.send(CMD_FADE_OUT_BASE | ch)
        time.sleep(FADE_DURATION_S + 0.2)
        for ch in range(1, NUM_CHANNELS + 1):
            self.send(CMD_STOP_FADE_BASE | ch)

    def close(self):
        self.spi.close()


# ------------------------------------------------------- research protocol ---

# FLS 60-minute stroboscopic protocol (from fls_60min_rp2350b.ino research).
# AMOS1+2 (GPIO 33+34) fire in sync as one combined output for max intensity.
# Pi sends CMD_DUAL_ON / CMD_DUAL_OFF (non-blocking) with precise timing to
# control frequency and duty cycle. RP2350 executes each command instantly.

from dataclasses import dataclass

@dataclass
class ProtocolStep:
    duration_s: float    # seconds
    start_freq: float    # Hz
    end_freq: float      # Hz
    start_duty: float    # 0.0-1.0
    end_duty: float      # 0.0-1.0
    oscillating: bool = False
    osc_rate_hz: float = 0.0

# 16-phase research protocol (60 min total, v3: max-intensity, fixed 50%
# duty cycle, 5.0-14.0 Hz range, from fls_60min_rp2350b-v3.ino)
FLS_PROTOCOL = [
    # Phase I: Induction (0-8 min)
    ProtocolStep(240, 14.0, 10.0, 0.50, 0.50),           # ramp-in
    ProtocolStep(240, 10.0, 10.0, 0.50, 0.50),           # alpha pure
    # Phase II: Alternation (8-24 min)
    ProtocolStep(180,  5.0,  5.0, 0.50, 0.50),           # theta immersion
    ProtocolStep(180,  5.0, 12.0, 0.50, 0.50),           # ascending sweep
    ProtocolStep(240, 10.2, 10.2, 0.50, 0.50, True, 0.1), # alpha harmonic oscillation
    ProtocolStep(180,  5.2,  5.2, 0.50, 0.50),           # theta sustained
    ProtocolStep(180, 14.0, 14.0, 0.50, 0.50),           # beta max stimulation
    # Phase III: Rhythmic variation (24-48 min)
    ProtocolStep(240, 10.0, 10.0, 0.50, 0.50, True, 0.25), # fast alternation
    ProtocolStep(240,  8.0, 11.0, 0.50, 0.50, True, 0.05), # floating sweep
    ProtocolStep(240,  5.5,  5.5, 0.50, 0.50),           # theta secondary
    ProtocolStep(240, 10.0, 10.0, 0.50, 0.50),           # alpha bright constant
    ProtocolStep(240, 12.0, 14.0, 0.50, 0.50),           # ramp to high beta
    ProtocolStep(240,  9.5,  9.5, 0.50, 0.50),           # return to alpha
    # Phase IV: Cooldown (48-60 min)
    ProtocolStep(240,  7.5,  6.0, 0.50, 0.50),           # intermediate transition
    ProtocolStep(240,  5.5,  5.0, 0.50, 0.30),           # power descent
    ProtocolStep(240,  5.0,  5.0, 0.30, 0.00),           # progressive shutdown
]


def fls_strobe(dev: RP2350, stop_event: threading.Event) -> None:
    """Run the FLS protocol on AMOS1+2 in sync, looping forever.
    Sends CMD_DUAL_ON / CMD_DUAL_OFF (non-blocking firmware commands) with
    precise Pi-side timing to achieve the research-specified frequency and
    duty cycle. (CMD_DUAL_PULSE is firmware-fixed at 100ms and blocks the
    SPI command loop, so it cannot do variable duty cycles.)"""
    import math

    try:
        while not stop_event.is_set():
            for step in FLS_PROTOCOL:
                if stop_event.is_set():
                    return
                step_start = time.monotonic()
                while True:
                    elapsed = time.monotonic() - step_start
                    if elapsed >= step.duration_s or stop_event.is_set():
                        break
                    progress = elapsed / step.duration_s
                    freq = step.start_freq + (step.end_freq - step.start_freq) * progress
                    duty = step.start_duty + (step.end_duty - step.start_duty) * progress
                    if step.oscillating:
                        freq += 0.5 * math.sin(2 * math.pi * step.osc_rate_hz * elapsed)
                    if freq <= 0 or duty <= 0:
                        time.sleep(0.1)
                        continue
                    period = 1.0 / freq
                    on_time = period * duty
                    off_time = period - on_time
                    # Both channels ON (sync)
                    dev.send(CMD_DUAL_ON)
                    _precise_sleep(on_time, stop_event)
                    # Both channels OFF
                    dev.send(CMD_DUAL_OFF)
                    _precise_sleep(off_time, stop_event)
    finally:
        dev.send(CMD_DUAL_OFF)


def _precise_sleep(seconds: float, stop_event: threading.Event) -> None:
    """Sleep with early exit on stop event, sub-ms precision."""
    end = time.monotonic() + seconds
    while True:
        remaining = end - time.monotonic()
        if remaining <= 0 or stop_event.is_set():
            return
        time.sleep(min(remaining, 0.001))


class PatternEngine:
    """Runs the FLS research protocol on AMOS1+2. FLS is permanent: it starts
    automatically on launch and has no runtime stop/override — only process
    shutdown (SIGTERM/systemd stop) ends it."""

    def __init__(self, dev: RP2350):
        self.dev = dev
        self._fls_stop = threading.Event()
        self._fls_thread = None

    def start_fls(self):
        """Start the 60-min FLS stroboscopic protocol (AMOS1+2 in sync)."""
        self._fls_stop.clear()
        self._fls_thread = threading.Thread(
            target=fls_strobe, args=(self.dev, self._fls_stop), daemon=True)
        self._fls_thread.start()

    def stop(self):
        """Shutdown only — stops the FLS thread and lets caller turn LEDs off."""
        self._fls_stop.set()
        if self._fls_thread and self._fls_thread.is_alive():
            self._fls_thread.join(timeout=3)


# ----------------------------------------------------------------- main ----

def main():
    dev = RP2350()
    engine = PatternEngine(dev)

    def shutdown(_signum=None, _frame=None):
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, shutdown)

    # FLS is the only mode: starts automatically, runs forever, no override
    engine.start_fls()
    print(f"led_controller_spi: FLS 60-min protocol started (permanent, "
          f"{NUM_CHANNELS} channels via SPI{SPI_BUS}.CS{SPI_CS}, no OSC/override)")

    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        pass
    finally:
        engine.stop()
        dev.all_off()
        dev.close()


if __name__ == "__main__":
    main()
