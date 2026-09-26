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
CMD_FADE_IN_BASE = 0x50    # | channel (1-6)
CMD_FADE_OUT_BASE = 0x60   # | channel
CMD_STOP_FADE_BASE = 0x70  # | channel

# Timing
FADE_DURATION_S = 1.0      # firmware fade time (~1 s)
IDLE_PERIOD_S = 2.5        # ambient: start a new fade every N seconds
PLAY_PERIOD_S = 0.6        # playing: faster pattern
PLAY_MAX_ACTIVE = 4        # max channels simultaneously lit while playing

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
                self._step_idle()
                time.sleep(IDLE_PERIOD_S)

    def _step_idle(self):
        """Slow breathing: keep at most one channel fading at a time."""
        if self._lit:
            ch = self._lit.pop()
            self.dev.fade_out(ch)
        else:
            ch = random.randint(1, NUM_CHANNELS)
            self.dev.fade_in(ch)
            self._lit.add(ch)

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
