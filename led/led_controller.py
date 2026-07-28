#!/usr/bin/env python3
"""
led_controller.py — OSC-driven LED strip controller for DREAMMACHINE.

Runs a continuous ambient breathing pattern across the configured GPIO pins
(via gpiozero/lgpio software PWM) and reacts to REAPER transport state
received over OSC (ReaOSC control surface): brighter/livelier while playing,
calm idle breathing while stopped.

Config is read from config/dreammachine.env (see that file for LED_PINS,
brightness range, OSC host/port).

Uses gpiozero (backed by lgpio) rather than pigpio: Raspberry Pi OS "trixie"
no longer packages pigpio/pigpiod (unmaintained upstream) — gpiozero+lgpio is
the Raspberry Pi Foundation's supported replacement and needs no daemon.

Restart policy: this script is meant to run under systemd
(dreammachine-led.service) with Restart=always. It installs a SIGTERM
handler so `systemctl stop` / `pkill -f led_controller.py` / reboot always
run the cleanup path (all LEDs off + GPIO pins released) instead of leaving
the last PWM duty cycle latched on the MOSFETs.
"""
import math
import os
import signal
import sys
import threading
import time
from pathlib import Path

from gpiozero import PWMLED
from pythonosc.dispatcher import Dispatcher
from pythonosc.osc_server import ThreadingOSCUDPServer

REPO_ROOT = Path(__file__).resolve().parent.parent
ENV_PATH = REPO_ROOT / "config" / "dreammachine.env"


def load_env(path: Path) -> dict:
    """Minimal .env parser (KEY=VALUE per line, '#' comments, no quoting)."""
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw_line in path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, _, val = line.partition("=")
        # Support simple ${VAR} expansion against already-loaded values/env.
        val = os.path.expandvars(val.strip())
        for k, v in values.items():
            val = val.replace("${" + k + "}", v)
        values[key.strip()] = val
    return values


ENV = load_env(ENV_PATH)


def env_str(key: str, default: str) -> str:
    return os.environ.get(key, ENV.get(key, default))


def env_int(key: str, default: int) -> int:
    return int(env_str(key, str(default)))


LED_PINS = [int(p) for p in env_str("LED_PINS", "12,13,16,17,22,27").split(",") if p]
MIN_BRIGHTNESS = env_int("LED_MIN_BRIGHTNESS", 10)  # percent, floor glow
MAX_BRIGHTNESS = env_int("LED_MAX_BRIGHTNESS", 100)  # percent
PWM_FREQ_HZ = env_int("LED_PWM_FREQ_HZ", 200)

OSC_LISTEN_HOST = env_str("OSC_LISTEN_HOST", "127.0.0.1")
OSC_LISTEN_PORT = env_int("OSC_LISTEN_PORT", 9000)

RESERVED_PINS = {0, 1, 18, 19, 20, 21}  # Audio+ V3 shield (EEPROM + I2S) — never use these.

# --- shared transport state, updated by the OSC listener thread ---
state_lock = threading.Lock()
transport = {"playing": False, "vu": [0.0] * 8}  # vu[0..7] ~ per-track/channel level 0..1

leds: list[PWMLED] = []
running = True


def set_all(pct: float) -> None:
    value = max(0.0, min(100.0, pct)) / 100.0
    for led in leds:
        led.value = value


def all_off() -> None:
    for led in leds:
        led.off()


def shutdown(signum=None, frame=None):
    # Raised from SIGTERM so it flows through the same cleanup path as
    # KeyboardInterrupt / normal exit. See repo memory: leaving PWM running
    # after the process dies keeps MOSFETs/LEDs latched on.
    raise KeyboardInterrupt


def ambient_loop() -> None:
    """Continuous breathing pattern; brighter/faster while REAPER is playing,
    with brightness additionally nudged by the live VU average while playing."""
    phase = 0.0
    while running:
        with state_lock:
            playing = transport["playing"]
            vu_avg = sum(transport["vu"]) / len(transport["vu"]) if playing else 0.0

        if playing:
            speed = 0.06
            low, high = MIN_BRIGHTNESS + 15, MAX_BRIGHTNESS
        else:
            speed = 0.02
            low, high = MIN_BRIGHTNESS, MIN_BRIGHTNESS + 30

        # Simple sine breathing between low and high, nudged upward by the
        # live VU average (0..1) so the strip visibly reacts to playback level.
        phase += speed
        brightness = low + (high - low) * (0.5 + 0.5 * math.sin(phase))
        if playing:
            brightness = min(MAX_BRIGHTNESS, brightness + vu_avg * 20)
        set_all(brightness)
        time.sleep(0.03)


def handle_play(address, *args):
    value = args[0] if args else 1.0
    with state_lock:
        transport["playing"] = bool(value)


def handle_stop(address, *args):
    with state_lock:
        transport["playing"] = False


def handle_pause(address, *args):
    value = args[0] if args else 1.0
    with state_lock:
        transport["playing"] = not bool(value)


def handle_vu(address, *args):
    # Default ReaperOSC pattern: /track/{n}/vu -> float 0..1
    try:
        track_idx = int(address.split("/")[2]) - 1
    except (IndexError, ValueError):
        return
    if 0 <= track_idx < len(transport["vu"]) and args:
        with state_lock:
            transport["vu"][track_idx] = float(args[0])


def build_osc_server() -> ThreadingOSCUDPServer:
    dispatcher = Dispatcher()
    dispatcher.map("/play", handle_play)
    dispatcher.map("/stop", handle_stop)
    dispatcher.map("/pause", handle_pause)
    dispatcher.map("/track/*/vu", handle_vu)
    return ThreadingOSCUDPServer((OSC_LISTEN_HOST, OSC_LISTEN_PORT), dispatcher)


def main() -> int:
    global running

    used_reserved = sorted(set(LED_PINS) & RESERVED_PINS)
    if used_reserved:
        print(
            f"FATAL: LED_PINS includes pins reserved by the Audio+ shield: {used_reserved}. "
            "Fix config/dreammachine.env (LED_PINS).",
            file=sys.stderr,
        )
        return 1

    try:
        for pin in LED_PINS:
            leds.append(PWMLED(pin, frequency=PWM_FREQ_HZ))
    except Exception as exc:  # noqa: BLE001 - fail loudly on any GPIO setup error
        print(f"FATAL: could not initialize GPIO pins {LED_PINS}: {exc}", file=sys.stderr)
        return 1

    signal.signal(signal.SIGTERM, shutdown)

    server = build_osc_server()
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    print(f"OSC listening on {OSC_LISTEN_HOST}:{OSC_LISTEN_PORT}, LED pins {LED_PINS}")

    ambient_thread = threading.Thread(target=ambient_loop, daemon=True)
    ambient_thread.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        running = False
        server.shutdown()
        all_off()
        for led in leds:
            led.close()
        print("LED controller stopped, all pins off.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
