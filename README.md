# Dreammachine_Rpi_popo

> **HARDWARE HOLD:** Do not apply external 12 V to any custom shield until
> R78/R79/R81 control nets and C65/C67 single-ended inputs have been reworked
> and signed off using [AMP_TEST.md](AMP_TEST.md). PCM5102A pin 17 `XSMT` must
> also be tied to `+3.3VDAC` per [DAC_TEST.md](DAC_TEST.md). USB-C logic-only
> operation is allowed.

Raspberry Pi control system for **DREAMMACHINE**, for an art installation. Each Pi runs a REAPER session through the custom PCM5102A
sound shield, while a Python service drives a synchronized LED strip, reacting
live to REAPER's transport/playback state over OSC (ReaOSC). The whole thing
boots unattended, kiosk-style — no keyboard, mouse, or monitor required on site.

Reference build: **sjcdm1** (unit 1). Once verified end-to-end, the exact same
setup is cloned to 4 more identical Pis — see [MIGRATION.md](MIGRATION.md).

```mermaid
flowchart LR
  A["REAPER project"] --> B["Master mono sum"]
  B -->|"ALSA / I2S"| C["PCM5102A DAC"]
  C -->|"OUTL"| D["TPA3118 left channel"]
  D --> E["AUDIOOUT1 pins 1-2\n8 ohm speaker"]
  C -.->|"OUTR unused"| F["TPA3118 right channel\nno load"]
  G["Raspberry Pi"] -->|"SPI0"| H["RP2350B controller"]
  H -->|"SDZ / MUTE"| D
  H -->|"GPIO33-38"| I["MOSFET outputs"]
```

The installation is **mono, left output only**. REAPER sums its master to
centered mono at runtime. Never parallel or bridge the TPA3118 left and right
outputs; leave AUDIOOUT1 pins 3-4 disconnected.

```mermaid
sequenceDiagram
  participant Boot as Pi boot
  participant RP as RP2350B
  participant R as REAPER wrapper
  participant DAC as PCM5102A / ALSA
  participant AMP as TPA3118

  Boot->>RP: Power/reset
  RP->>AMP: MUTE high, SDZ low
  Boot->>R: X11 autostart
  R->>RP: amp-mute + amp-shutdown
  R->>RP: amp-start-muted
  R->>DAC: Launch REAPER
  DAC-->>R: PCM device owned
  R->>R: Force master to centered mono
  R->>RP: amp-unmute
  RP->>AMP: Unmute only if FAULTZ high
```

```mermaid
flowchart TD
  A["REAPER running"] --> B{"FAULTZ high?"}
  B -->|"Yes"| C["Left mono audio enabled"]
  B -->|"No"| D["Remain muted"]
  C --> E{"REAPER exits or wrapper stops?"}
  E -->|"No"| A
  E -->|"Yes"| F["MUTE high"]
  D --> F
  F --> G["SDZ low / amplifier shutdown"]
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
| OS | Raspberry Pi OS (Debian 13 "trixie"), 64-bit, desktop (X11/Openbox — see Troubleshooting) |
| Sound shield | Custom PCM5102A (`hifiberry-dac` overlay, ALSA `snd_rpi_hifiberry_dac`) |
| LED control | RP2350B GPIO33-38; Raspberry Pi control over SPI is the next integration step |

**GPIO 18, 19, and 21 are reserved for PCM5102A I2S. GPIO16-20 are reserved
for RP2350B SPI/IRQ, and GPIO0/1 are reserved for serial communication.** The
existing `dreammachine-led.service` is legacy direct-GPIO code and must remain
stopped with the custom shield until it is replaced by the RP2350 SPI client.

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
bash setup/01_audio_dac.sh        # enable PCM5102A overlay; reboot and run again to test
bash setup/02_install_reaper.sh   # download + install REAPER (aarch64 eval)
bash setup/04_vnc_and_autostart.sh  # enable VNC, kiosk autologin, REAPER autostart
bash setup/05_install_reaper_extensions.sh  # SWS/S&M + ReaPack (restart REAPER after)
```
Or run all at once: `bash setup/run_all.sh`

Do not run `setup/03_led_service.sh` on the custom shield. It belongs to the
older direct-GPIO design and will be replaced by the RP2350B SPI service.

After `02_install_reaper.sh`, REAPER must be **launched once via VNC/HDMI** to
create `reaper.ini`, then the audio device and OSC control surface are
configured manually (see [reaper/OSC_SETUP.md](reaper/OSC_SETUP.md)) — this
only needs doing once, then `reaper.ini` is copied verbatim to the other Pis.

Before connecting speakers or enabling the amplifier, complete the repeatable
[PCM5102A DAC acceptance test](DAC_TEST.md) on each unit.

Before applying 12 V, complete the mandatory control-net rework and staged
[TPA3118D2 amplifier test](AMP_TEST.md).

RP2350B firmware flashing, the SPI pin map, command protocol, and pattern test
are documented in [RP2350.md](RP2350.md).

## REAPER extensions (SWS/S&M + ReaPack)

`setup/05_install_reaper_extensions.sh` installs two community-standard REAPER
extensions straight into `~/.config/REAPER/UserPlugins/`:

- **[SWS/S&M](https://www.sws-extension.org/)** (`reaper_sws-aarch64.so`) — a large
  bundle of extra actions, tools and utilities (batch processing, extra track/item
  management, grooves, notes, etc.) that most non-trivial REAPER setups rely on.
- **[ReaPack](https://reapack.com/)** (`reaper_reapack-aarch64.so`) — REAPER's
  package manager. It lets REAPER pull in and auto-update community scripts,
  JSFX effects, and themes from public repositories, instead of copying files by
  hand.

Both are official aarch64 Linux builds (SWS's bleeding-edge build page publishes
the only aarch64 binary available; ReaPack's GitHub release provides one
directly). ⚠️ The ReaPack `.so` **must** keep its `-aarch64` filename suffix —
renaming it triggers a "not loaded from the standard extension path" warning,
since ReaPack uses that suffix to find the right asset for its own self-updates.

Once installed (REAPER needs a restart to load new extensions), use
**Extensions > ReaPack > Synchronize packages** to pull in the package
index, then **Extensions > ReaPack > Browse packages** to search and install
any additional scripts/JSFX from the community repositories — this is how
REAPER's functionality gets extended going forward without editing this repo.

## Tremor sound source (real seismic sonification)

`reaper/tremor_samples/` contains real ground-motion audio generated with
[DZA01](https://github.com/RVX/DZA_Borehole_Sonification), a GPL-3.0 sonification
toolkit that pulls live seismic data from the DZA borehole network (KIT/GPI,
Germany) and speeds it up into the audible range (a straight frequency shift,
no synthesis). One clip per site/depth combination, 3 minutes each, 0.5–10 Hz
bandpass, 100x speed-up, vertical channel:

| File | Site | Sensor |
|---|---|---|
| `tremor_DZA11_surface_vertical.wav` | Site 1 | surface (Trillium Compact 20s) |
| `tremor_DZA13_borehole_vertical.wav` | Site 1 | borehole, ~240 m depth |
| `tremor_DZA31_surface_vertical.wav` | Site 3 | surface (Trillium Horizon 120s) |
| `tremor_DZA33_borehole_vertical.wav` | Site 3 | borehole, ~240 m depth |

Import these into the REAPER project as audio items to use as ambient/tremor
material (the borehole clips are quieter/deeper-feeling; the surface clips
carry more transient detail). Regenerate or fetch a fresh/longer window any
time with the toolkit itself, e.g.:
```bash
python DZA01.py --sites 1,3 --listen-minutes 3 --channel all fetch plot sonify
```

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

**Drag-and-drop into REAPER doesn't work (Insert > Media File does)**: the
default Raspberry Pi OS desktop session is `labwc` (Wayland); REAPER is an
X11-only app and runs under it via XWayland. Drag-and-drop across the
XWayland↔native-Wayland boundary (e.g. from the file manager) is unreliable on
wlroots-based compositors like labwc — this happens with a directly-connected
mouse/keyboard too, it isn't VNC-specific. `setup/04_vnc_and_autostart.sh`
switches the session to plain X11 (`raspi-config nonint do_wayland W1`,
Openbox) instead, which avoids the problem entirely; REAPER's autostart is
then configured via `~/.config/lxsession/rpd-x/autostart` +
`systemd/start_reaper.sh` rather than a labwc autostart file.

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
