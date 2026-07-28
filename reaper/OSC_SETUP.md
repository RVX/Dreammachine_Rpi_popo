# REAPER OSC Setup (ReaOSC) — one-time manual step per reference build

This can only be done through REAPER's GUI (via VNC or HDMI+keyboard/mouse on
the Pi), so it's a manual step done **once** on `sjcdm1`. The resulting
`~/.config/REAPER/reaper.ini` is then copied verbatim to the other 4 Pis
during migration (see [../MIGRATION.md](../MIGRATION.md)) — no need to repeat
this on every unit.

## Expected errors on first boot (before this is done) — normal, ignore

- **"Error opening devices... error opening audio hardware... JACK error
  creating client"**: REAPER auto-detects available audio backends on first
  launch and picks **JACK** because `libjack-jackd2-0` is installed as a
  dependency (no actual JACK server runs on this Pi). Fixed in Step 1 below.
- **"There was an error opening the project: Dreammachine_popo_01.RPP"**:
  the autostart script always points at this path, but the file doesn't
  exist until you do **File > Save As** in Step 2. This warning will stop
  appearing for good once the project is saved there.

## Steps

1. Connect via VNC (RealVNC Viewer, port 5900) to the Pi's IP, or plug in a
   monitor/keyboard/mouse directly.
2. Launch REAPER from the desktop menu (Sound & Video > REAPER), or run
   `reaper` from a terminal. This creates `~/.config/REAPER/reaper.ini` if it
   doesn't already exist.
3. **Fix the audio device** (Preferences > Audio > Device, `Ctrl+P`):
   - **Audio System**: `ALSA`
   - **Input/Output Device**: `hw:3,0 (HifiBerry DAC HiFi)` (the Audio+ V3
     shield — matches `ALSA_CARD_NAME=sndrpihifiberry` in
     `config/dreammachine.env`)
   - Click **Apply**, then confirm no error dialog appears. This permanently
     fixes the JACK error above.
4. Open **Preferences** (`Ctrl+P`) > **Control/OSC/web**.
5. Click **Add**.
6. Control surface mode: **OSC (ReaOSC)**.
7. Settings:
   - **Device name**: `dreammachine-led`
   - **Device IP**: `127.0.0.1` (LED script runs locally on the same Pi)
   - **Device port**: `9001` (REAPER listens here, only needed if the LED
     script ever sends OSC back — matches `OSC_REAPER_PORT` in
     `config/dreammachine.env`)
   - **Local listen port**: `9000` (REAPER sends OSC here — matches
     `OSC_LISTEN_PORT` in `config/dreammachine.env`)
   - **Pattern config**: `Default.ReaperOSC` (ships with REAPER, provides
     `/play`, `/stop`, `/pause`, `/track/{n}/vu`, etc. — this is what
     `led/led_controller.py` listens for)
7. Click **OK**, then **OK** again to close Preferences.
8. Open/create the project named exactly `Dreammachine_popo_01` (see
   `config/dreammachine.env` → `REAPER_PROJECT_NAME`) and **Save As** to
   `${REAPER_PROJECT_DIR}` (`/home/sjc/reaper-projects/Dreammachine_popo_01/`).
9. Press play/stop in REAPER and confirm the LED controller reacts (check
   `journalctl -u dreammachine-led.service -f` on the Pi — you should see no
   errors, and if wired to real LEDs, the breathing pattern should speed up
   and brighten while playing).

## Backing up the OSC config for migration

```bash
# From your PC:
scp -i "$env:USERPROFILE\.ssh\id_ed25519_dreammachine" -o IdentitiesOnly=yes `
  sjc@192.168.88.104:/home/sjc/.config/REAPER/reaper.ini .\reaper\reaper.ini.sjcdm1
```
Keep this as the template `reaper.ini` to copy onto Pi 2-5's
`~/.config/REAPER/reaper.ini` after their own first REAPER launch (which
creates the default file/folder structure).
