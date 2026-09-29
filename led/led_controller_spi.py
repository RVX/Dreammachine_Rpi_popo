#!/usr/bin/env python3
"""
led_controller_spi.py — OSC-driven LED controller for DREAMMACHINE (RP2350 SPI).

Listens for REAPER transport state over OSC (ReaOSC control surface) and
drives the 6 MOSFET LED channels through the RP2350B coprocessor over SPI0:
  - Playing  -> lively random fade pattern across channels
  - Stopped  -> slow ambient breathing (one channel fading at a time)

The RP2350 firmware owns all PWM timing — this script only sends single-byte
commands (fade in/out, all off), which are non-blocking on the firmware side.

Command set (must match rp2350/main.c):
  0x00        all off + amp shutdown
  0x01-0x06   pulse ch1-6 (500 ms)
  0x51-0x56   fade IN ch1-6 (non-blocking, ~1 s)
  0x61-0x66   fade OUT ch1-6
  0x71-0x76   stop fade ch1-6

Config: config/dreammachine.env (OSC_LISTEN_HOST/PORT, LED channels count).

Restart policy: runs under systemd (dreammachine-led.service, Restart=always).
SIGTERM handler ensures cleanup path (all off) runs on stop/reboot.
"""
import random
import signal
import threading
import time
from pathlib import Path

import spidev
from pythonosc.dispatcher import Dispatcher
from pythonosc.osc_server import ThreadingOSCUDPServer

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

OSC_HOST = ENV.get("OSC_LISTEN_HOST", "127.0.0.1")
OSC_PORT = int(ENV.get("OSC_LISTEN_PORT", "9000"))
NUM_CHANNELS = int(ENV.get("LED_NUM_CHANNELS", "6"))

SPI_BUS = 0
SPI_CS = 0
SPI_SPEED = 500_000

# Firmware commands
CMD_ALL_OFF = 0x00
CMD_PULSE_BASE = 0x00        # | channel (1-6) = 0x01-0x06 pulse 500ms
CMD_DUAL_PULSE = 0x07        # both AMOS1+2 100ms (kick sync)
CMD_DUAL_ON = 0x08           # AMOS1+2 held ON  (non-blocking, FLS strobe)
CMD_DUAL_OFF = 0x09          # AMOS1+2 OFF      (non-blocking, FLS strobe)
CMD_FADE_IN_BASE = 0x50      # | channel (1-6)
CMD_FADE_OUT_BASE = 0x60     # | channel
CMD_STOP_FADE_BASE = 0x70    # | channel

# Timing
FADE_DURATION_S = 1.0      # firmware fade time (~1 s)
PLAY_PERIOD_S = 0.6        # playing: faster pattern
PLAY_MAX_ACTIVE = 4        # max channels simultaneously lit while playing

# AMOS channels (GPIO33, GPIO34 on RP2350)
AMOS1 = 1
AMOS2 = 2

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


# ------------------------------------------------------------- patterns ----

# ------------------------------------------------------- research protocol ---

# FLS 60-minute stroboscopic protocol (from fls_60min_rp2350b.ino research).
# AMOS1+2 (GPIO 33+34) fire in sync as one combined output for max intensity.
# Pi sends CMD_DUAL_ON / CMD_DUAL_OFF (non-blocking) with precise timing to
# control frequency and duty cycle. RP2350 executes each command instantly.

from dataclasses import dataclass
from typing import Generator, Tuple

@dataclass
class ProtocolStep:
    duration_s: float    # seconds
    start_freq: float    # Hz
    end_freq: float      # Hz
    start_duty: float    # 0.0-1.0
    end_duty: float      # 0.0-1.0
    oscillating: bool = False
    osc_rate_hz: float = 0.0

# 16-phase research protocol (60 min total, from the .ino reference)
FLS_PROTOCOL = [
    # Phase I: Induction (0-8 min)
    ProtocolStep(240, 14.0, 10.0, 0.20, 0.30),           # ramp-in
    ProtocolStep(240, 10.0, 10.0, 0.30, 0.30),           # alpha pure
    # Phase II: Alternation (8-24 min)
    ProtocolStep(180,  3.5,  3.5, 0.50, 0.50),           # theta hypnagogic
    ProtocolStep(180,  3.5, 12.0, 0.50, 0.30),           # ascending sweep
    ProtocolStep(240, 10.2, 10.2, 0.30, 0.30, True, 0.1), # alpha harmonic oscillation
    ProtocolStep(180,  3.0,  3.0, 0.50, 0.50),           # theta deep / CVH
    ProtocolStep(180, 15.0, 15.0, 0.25, 0.25),           # beta stimulation
    # Phase III: Rhythmic variation (24-48 min)
    ProtocolStep(240, 10.0, 10.0, 0.30, 0.30, True, 0.25), # fast alternation
    ProtocolStep(240,  9.0,  9.0, 0.35, 0.35, True, 0.05), # floating alpha/theta sine
    ProtocolStep(240,  3.2,  3.2, 0.50, 0.50),           # hypnagogic immersion 2
    ProtocolStep(240, 10.0, 10.0, 0.20, 0.40),           # alpha bright, duty sweep
    ProtocolStep(240, 16.0, 18.0, 0.20, 0.25),           # ramp to high beta
    ProtocolStep(240,  9.5,  9.5, 0.30, 0.30),           # return to relaxed alpha
    # Phase IV: Cooldown (48-60 min)
    ProtocolStep(240,  8.0,  6.0, 0.35, 0.35),           # intermediate transition
    ProtocolStep(240,  5.0,  2.0, 0.35, 0.20),           # gradual descent
    ProtocolStep(240,  2.0,  0.2, 0.20, 0.00),           # shutdown to baseline
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
    """Ambient/playing fade choreography + FLS research protocol on RP2350."""

    def __init__(self, dev: RP2350):
        self.dev = dev
        self.playing = False
        self.fls_active = False  # True when running the 60-min FLS protocol
        self._stop = threading.Event()
        self._fls_stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._fls_thread = None
        self._lit = set()  # channels currently fading in / lit

    def start(self):
        self._thread.start()

    def stop(self):
        self._stop.set()
        self._fls_stop.set()
        self._thread.join(timeout=3)
        if self._fls_thread and self._fls_thread.is_alive():
            self._fls_thread.join(timeout=3)

    def set_playing(self, playing: bool):
        if playing != self.playing:
            self.playing = playing
            for ch in list(self._lit):
                self.dev.fade_out(ch)
            self._lit.clear()

    def start_fls(self):
        """Start the 60-min FLS stroboscopic protocol (AMOS1+2 in sync)."""
        self.stop_fls()
        self.fls_active = True
        self._fls_stop.clear()
        self._fls_thread = threading.Thread(
            target=fls_strobe, args=(self.dev, self._fls_stop), daemon=True)
        self._fls_thread.start()

    def stop_fls(self):
        """Stop the FLS protocol and return to ambient mode."""
        self.fls_active = False
        self._fls_stop.set()
        if self._fls_thread and self._fls_thread.is_alive():
            self._fls_thread.join(timeout=3)

    def _run(self):
        while not self._stop.is_set():
            if self.fls_active:
                # FLS protocol running in its own thread — just wait
                time.sleep(0.5)
            elif self.playing:
                self._step_playing()
                time.sleep(PLAY_PERIOD_S)
            else:
                self._step_idle_sequence()

    # ---- Idle choreography: varied patterns cycling on AMOS1+2 ----
    # Each pattern is a generator that yields (action_fn, duration_s) steps.
    # The engine runs through all steps, then moves to the next pattern.

    def _pattern_fade_each(self):
        """Slow fade in/out on each channel, one at a time."""
        for ch in (AMOS1, AMOS2):
            yield (lambda c=ch: self.dev.fade_in(c), FADE_DURATION_S + 1.0)
            yield (lambda c=ch: self.dev.fade_out(c), FADE_DURATION_S + 1.5)

    def _pattern_fade_both(self):
        """Both channels fade in together, hold, fade out together."""
        yield (lambda: (self.dev.fade_in(AMOS1), self.dev.fade_in(AMOS2)), FADE_DURATION_S + 2.0)
        yield (lambda: (self.dev.fade_out(AMOS1), self.dev.fade_out(AMOS2)), FADE_DURATION_S + 2.0)

    def _pattern_crossfade(self):
        """AMOS1 fades in as AMOS2 fades out, then reverse."""
        yield (lambda: (self.dev.fade_in(AMOS1), self.dev.fade_out(AMOS2)), FADE_DURATION_S + 1.0)
        yield (lambda: (self.dev.fade_out(AMOS1), self.dev.fade_in(AMOS2)), FADE_DURATION_S + 1.0)

    def _pattern_fast_blink(self):
        """Rapid dual pulses (~5 Hz strobe) for 3 seconds."""
        for _ in range(30):
            yield (lambda: self.dev.send(CMD_DUAL_PULSE), 0.1)

    def _pattern_pulse_train(self, hz, count):
        """Alternating pulses at given frequency."""
        interval = 1.0 / hz
        for i in range(count):
            ch = AMOS1 if i % 2 == 0 else AMOS2
            yield (lambda c=ch: self.dev.send(CMD_PULSE_BASE | c), interval)

    def _pattern_dual_pulse_slow(self):
        """Dual pulses at 4 Hz."""
        yield from self._pattern_pulse_train(4, 8)

    def _pattern_dual_pulse_fast(self):
        """Dual pulses at 8 Hz."""
        yield from self._pattern_pulse_train(8, 16)

    # ---- New aggressive patterns ----

    def _pattern_strobe_burst(self):
        """Ultra-fast strobe on both channels (~20 Hz) for 1.5s."""
        for _ in range(30):
            yield (lambda: self.dev.send(CMD_DUAL_PULSE), 0.05)

    def _pattern_max_min_swing(self):
        """Alternate max brightness both, then near-dark both. Hard contrast."""
        for _ in range(4):
            yield (lambda: (self.dev.fade_in(AMOS1), self.dev.fade_in(AMOS2)), 0.3)
            yield (lambda: (self.dev.fade_out(AMOS1), self.dev.fade_out(AMOS2)), 0.3)

    def _pattern_glitch(self):
        """Random rapid-fire pulses on random channels — glitchy/static feel."""
        for _ in range(40):
            ch = random.choice([AMOS1, AMOS2, AMOS1, AMOS2])  # 50/50
            delay = random.uniform(0.03, 0.15)
            yield (lambda c=ch: self.dev.send(CMD_PULSE_BASE | c), delay)

    def _pattern_sweep_up(self):
        """Pulse rate accelerates from 1 Hz to 12 Hz."""
        for hz in [1, 2, 3, 4, 5, 6, 8, 10, 12]:
            yield from self._pattern_pulse_train(hz, max(2, int(hz * 0.3)))

    def _pattern_sweep_down(self):
        """Pulse rate decelerates from 12 Hz to 1 Hz."""
        for hz in [12, 10, 8, 6, 4, 3, 2, 1]:
            yield from self._pattern_pulse_train(hz, max(2, int(hz * 0.3)))

    def _pattern_pingpong(self):
        """Rapid alternating single pulses AMOS1-AMOS2 at 10 Hz."""
        for i in range(40):
            ch = AMOS1 if i % 2 == 0 else AMOS2
            yield (lambda c=ch: self.dev.send(CMD_PULSE_BASE | c), 0.05)

    def _pattern_long_dark_pulse(self):
        """Long darkness, then single bright pulse. Ominous."""
        yield (lambda: (self.dev.fade_out(AMOS1), self.dev.fade_out(AMOS2)), 3.0)
        yield (lambda: self.dev.send(CMD_DUAL_PULSE), 0.5)
        yield (lambda: (self.dev.fade_out(AMOS1), self.dev.fade_out(AMOS2)), 2.0)
        yield (lambda: self.dev.send(CMD_DUAL_PULSE), 0.5)

    def _pattern_breathe_fast(self):
        """Fast shallow breathing — both channels, quick in/out."""
        for _ in range(6):
            yield (lambda: (self.dev.fade_in(AMOS1), self.dev.fade_in(AMOS2)), 0.5)
            yield (lambda: (self.dev.fade_out(AMOS1), self.dev.fade_out(AMOS2)), 0.5)

    def _step_idle_sequence(self):
        """Cycle through all idle patterns — calm to aggressive and back."""
        patterns = [
            self._pattern_fade_each,          # calm breathing
            self._pattern_crossfade,           # smooth swap
            self._pattern_dual_pulse_slow,     # 4 Hz rhythm
            self._pattern_breathe_fast,        # quick shallow
            self._pattern_glitch,              # random static
            self._pattern_sweep_up,            # 1→12 Hz acceleration
            self._pattern_strobe_burst,        # 20 Hz burst
            self._pattern_max_min_swing,       # hard contrast
            self._pattern_pingpong,            # fast alternating
            self._pattern_sweep_down,          # 12→1 Hz decel
            self._pattern_fade_both,           # calm together
            self._pattern_long_dark_pulse,     # ominous dark+hit
        ]
        for pattern_fn in patterns:
            if self.playing or self._stop.is_set():
                return
            for action, duration in pattern_fn():
                if self.playing or self._stop.is_set():
                    return
                action()
                time.sleep(duration)

    def _step_playing(self):
        """Livelier: randomly toggle channels, cap simultaneous active ones."""
        if len(self._lit) >= PLAY_MAX_ACTIVE or (self._lit and random.random() < 0.4):
            ch = random.choice(list(self._lit))
            self._lit.discard(ch)
            self.dev.fade_out(ch)
        else:
            choices = [c for c in range(1, NUM_CHANNELS + 1) if c not in self._lit]
            if choices:
                ch = random.choice(choices)
                self.dev.fade_in(ch)
                self._lit.add(ch)


# ------------------------------------------------------------------ OSC ----

def make_dispatcher(engine: PatternEngine) -> Dispatcher:
    disp = Dispatcher()

    def on_play(_addr, *_args):
        engine.set_playing(True)

    def on_stop(_addr, *_args):
        engine.set_playing(False)

    def on_fls_start(_addr, *_args):
        engine.start_fls()

    def on_fls_stop(_addr, *_args):
        engine.stop_fls()

    disp.map("/play", on_play)
    disp.map("/stop", on_stop)
    disp.map("/pause", on_stop)
    disp.map("/fls/start", on_fls_start)
    disp.map("/fls/stop", on_fls_stop)
    return disp


# ----------------------------------------------------------------- main ----

def main():
    dev = RP2350()
    engine = PatternEngine(dev)

    def shutdown(_signum=None, _frame=None):
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, shutdown)

    engine.start()
    server = ThreadingOSCUDPServer((OSC_HOST, OSC_PORT), make_dispatcher(engine))
    print(f"led_controller_spi: OSC listening on {OSC_HOST}:{OSC_PORT}, "
          f"{NUM_CHANNELS} channels via SPI{SPI_BUS}.CS{SPI_CS}")

    # FLS is the default mode: start automatically and loop forever
    engine.start_fls()
    print("led_controller_spi: FLS 60-min protocol started (default mode)")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        engine.stop()
        dev.all_off()
        dev.close()
        server.server_close()


if __name__ == "__main__":
    main()
