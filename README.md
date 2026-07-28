# Dreammachine_Rpi_popo

Raspberry Pi control system for **DREAMMACHINE**, for an art installation. Each Pi runs a REAPER session through a RaspiAudio Audio+ V3
sound shield, while a Python service drives a synchronized LED strip, reacting
live to REAPER's transport/playback state over OSC (ReaOSC). The whole thing
boots unattended, kiosk-style — no keyboard, mouse, or monitor required on site.

Reference build: **sjcdm1** (unit 1). Once verified end-to-end, the exact same
setup is cloned to 4 more identical Pis — see [MIGRATION.md](MIGRATION.md).

```mermaid
flowchart LR
    A["REAPER\n(Dreammachine_popo_01.RPP)"] -- "OSC :9000\n/play /stop /track/*/vu" --> B["led_controller.py\n(systemd service)"]
    A -- "ALSA" --> C["RaspiAudio Audio+ V3\n(I2S DAC)"]
    B -- "PWM (gpiozero/lgpio)" --> D["LED strip\nGPIO 12/13/16/17/22/27"]
    E["Boot"] -- "autologin + autostart" --> A
```

## Status

| Unit | Hostname | Audio | REAPER + OSC | LED service | Autoboot |
|---|---|---|---|---|---|
| 1 (reference) | sjcdm1 | ✅ | 🔄 in progress | ✅ | ✅ |
| 2-5 | TBD | ⬜ | ⬜ | ⬜ | ⬜ |

See [MIGRATION.md](MIGRATION.md) for the full fleet tracking table.

## Hardware / OS

| Item | Value |
|---|---|
| Board | Raspberry Pi 4 Model B Rev 1.5 |
| OS | Raspberry Pi OS (Debian 13 "trixie"), 64-bit, desktop (labwc/Wayland) |
| Sound shield | RaspiAudio Audio+ V3 (`snd_rpi_hifiberry_dac`, auto-detected via EEPROM, **no config.txt edit needed**) |
| LED strip | PWM MOSFET strip via `gpiozero`/`lgpio`, GPIO 12,13,16,17,22,27 (configurable) |

⚠️ **GPIO 18, 19, 20, 21 are reserved by the Audio+ shield's I2S bus** — never reuse
them for the LED strip or anything else. GPIO 0/1 are used by the shield's ID
EEPROM. Confirmed free/default LED pins: **12, 13, 16, 17, 22, 27**.

## Network

| Pi | Hostname | User | IP | SSH key |
|---|---|---|---|---|
| Unit 1 (reference) | sjcdm1 | sjc | 192.168.88.104 | `~/.ssh/id_ed25519_dreammachine` |
| Unit 2-5 | TBD | sjc | TBD | same key, once installed |

Password for `sjc` user: `sjcsjc` (only needed until the SSH key is installed).

SSH pattern (Windows PowerShell):
```powershell
$env:PATH += ";C:\Windows\System32\OpenSSH"
ssh -i "$env:USERPROFILE\.ssh\id_ed25519_dreammachine" -o IdentitiesOnly=yes -o StrictHostKeyChecking=no sjc@192.168.88.104
```

## Repo layout

```
setup/            install scripts, run once per Pi (idempotent)
config/           dreammachine.env — single source of config (pins, ports, paths)
led/              led_controller.py — OSC-driven LED controller (systemd service)
reaper/           placeholder project + OSC setup instructions
systemd/          unit files installed on the Pi
MIGRATION.md      steps to clone the working setup to Pi 2-5
```

## Setup order (on a fresh Pi)

```bash
bash setup/01_system_base.sh      # apt update/upgrade, gpiozero/lgpio, python venv, alsa
bash setup/02_install_reaper.sh   # download + install REAPER (aarch64 eval)
bash setup/03_led_service.sh      # venv + python-osc + systemd LED service
bash setup/04_vnc_and_autostart.sh  # enable VNC, kiosk autologin, REAPER autostart
bash setup/05_install_reaper_extensions.sh  # SWS/S&M + ReaPack (restart REAPER after)
```
Or run all at once: `bash setup/run_all.sh`

After `02_install_reaper.sh`, REAPER must be **launched once via VNC/HDMI** to
create `reaper.ini`, then the audio device and OSC control surface are
configured manually (see [reaper/OSC_SETUP.md](reaper/OSC_SETUP.md)) — this
only needs doing once, then `reaper.ini` is copied verbatim to the other Pis.

## Troubleshooting

**"Error opening devices... JACK error creating client"** on first boot: REAPER
auto-picks JACK as its audio system because `libjack-jackd2-0` is present
(pulled in as a dependency), even though no JACK server runs on the Pi. Fix
once via Preferences > Audio > Device > Audio System: `ALSA`, Device:
`hw:3,0` (see [reaper/OSC_SETUP.md](reaper/OSC_SETUP.md)).

**"There was an error opening the project: Dreammachine_popo_01.RPP"** on
first boot: expected until the project is saved for the first time via
**File > Save As** (see [reaper/OSC_SETUP.md](reaper/OSC_SETUP.md)) — the
autostart script always points at this path.

## Robustness measures

- `dreammachine-led.service` runs as a systemd service with `Restart=always`.
- LED script installs a `SIGTERM` handler so `systemctl stop` / reboot always
  turns the strip off cleanly instead of leaving the last PWM duty cycle
  latched on the MOSFETs.
- Pi boots straight to desktop (autologin, kiosk), REAPER autostarts and loads
  the project automatically — no keyboard/monitor needed on site.
- Hardware watchdog enabled (see `setup/04_vnc_and_autostart.sh`).

## License

Internal production tooling for the DREAMMACHINE installation. No license
granted for reuse outside the project unless stated otherwise by the author.

## Credits

Built for **DREAMMACHINE** by Víctor Mazón Gardoqui. 2026.
