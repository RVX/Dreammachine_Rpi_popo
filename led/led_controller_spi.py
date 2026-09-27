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

class PatternEngine:
    """Ambient/playing fade choreography on top of RP2350 fade commands."""

    def __init__(self, dev: RP2350):
        self.dev = dev
        self.playing = False
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._lit = set()  # channels currently fading in / lit

    def start(self):
        self._thread.start()

    def stop(self):
        self._stop.set()
        self._thread.join(timeout=3)

    def set_playing(self, playing: bool):
        if playing != self.playing:
            self.playing = playing
            # on transition, fade everything out and rebuild the pattern
            for ch in list(self._lit):
                self.dev.fade_out(ch)
            self._lit.clear()

    def _run(self):
        while not self._stop.is_set():
            if self.playing:
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

    disp.map("/play", on_play)
    disp.map("/stop", on_stop)
    # ReaOSC also sends /play with arg 1/0 on toggle in some configs
    disp.map("/pause", on_stop)
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
