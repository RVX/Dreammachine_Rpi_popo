# Migration — cloning the verified sjcdm1 build to Pi 2-5

> **12 V HOLD FOR ALL FIVE SHIELDS:** Complete the R78/R79/R81 control rework
> and C65/C67 input rework in [AMP_TEST.md](AMP_TEST.md) before any external
> 12 V test. Also connect PCM5102A `XSMT` to `+3.3VDAC` as documented in
> [DAC_TEST.md](DAC_TEST.md). These corrections cannot be replaced by firmware.

Once `sjcdm1` is fully tested end-to-end (audio via Audio+ shield, LED sync
via OSC, kiosk autostart, VNC access), replicate it to the remaining 4 Pis.

Two options — pick based on time available on site vs. remotely:

## Option A — SD card image clone (fastest, most identical)

Best when you have physical access to all Pis before installation.

1. Shut down `sjcdm1`: `sudo shutdown now`.
2. Remove its SD card, image it (e.g. Raspberry Pi Imager > "Use custom" or
   `dd`/Win32DiskImager) to a `.img` file.
3. Flash that image onto the other 4 SD cards.
4. Boot each Pi, then per-unit fix-ups only:
   - Change hostname: `sudo raspi-config nonint do_hostname <name>` (avoid
     duplicate hostnames on the network).
   - Regenerate SSH host keys so each Pi has unique ones:
     `sudo rm /etc/ssh/ssh_host_*; sudo dpkg-reconfigure openssh-server`.
   - If REAPER's evaluation/license is per-machine, re-enter the license (see
     REAPER > Help > About REAPER).
   - Run `bash setup/01_audio_dac.sh` and confirm `aplay -l` shows
     `sndrpihifiberry`. The script plays a quiet left/right DAC test.
   - Flash the RP2350B over SWD and run the SPI bounce test as documented in
     [RP2350.md](RP2350.md).

## Option B — scripted install (use if imaging isn't practical)

For each new Pi (fresh Raspberry Pi OS, `sjc` user already created):

```powershell
# From your PC — copy the repo over:
$env:PATH += ";C:\Windows\System32\OpenSSH"
scp -i "$env:USERPROFILE\.ssh\id_ed25519_dreammachine" -o IdentitiesOnly=yes -r `
  .\ sjc@<NEW_PI_IP>:/home/sjc/dreammachine

# Run the full setup:
ssh -i "$env:USERPROFILE\.ssh\id_ed25519_dreammachine" -o IdentitiesOnly=yes `
  sjc@<NEW_PI_IP> "cd /home/sjc/dreammachine && bash setup/run_all.sh"

# Copy the pre-configured OSC control surface (skips the manual GUI step):
ssh -i "$env:USERPROFILE\.ssh\id_ed25519_dreammachine" -o IdentitiesOnly=yes `
  sjc@<NEW_PI_IP> "mkdir -p /home/sjc/.config/REAPER"
scp -i "$env:USERPROFILE\.ssh\id_ed25519_dreammachine" -o IdentitiesOnly=yes `
  .\reaper\reaper.ini.sjcdm1 sjc@<NEW_PI_IP>:/home/sjc/.config/REAPER/reaper.ini

# Copy the project:
scp -i "$env:USERPROFILE\.ssh\id_ed25519_dreammachine" -o IdentitiesOnly=yes -r `
  .\reaper\Dreammachine_popo_01 sjc@<NEW_PI_IP>:/home/sjc/reaper-projects/

# Reboot to apply autologin/kiosk/watchdog:
ssh -i "$env:USERPROFILE\.ssh\id_ed25519_dreammachine" -o IdentitiesOnly=yes `
  sjc@<NEW_PI_IP> "sudo reboot"
```

Then verify: Pi boots to desktop unattended, REAPER autostarts and plays,
audio comes out the shield, the RP2350B responds to an SPI pattern command,
and VNC is reachable. The legacy `dreammachine-led.service` must remain
disabled until it is replaced by the SPI controller service.

Each unit is mono left-channel only. Connect the speaker to AUDIOOUT1 pins 1-2,
leave pins 3-4 open, and verify the startup wrapper applies the REAPER master
mono script before unmuting IC1.

## Fleet tracking

| Pi | Hostname | IP | SSH key | DAC/ALSA | RP2350 SWD | SPI pattern | REAPER+OSC |
|---|---|---|---|---|---|---|---|
| 1 | sjcdm1 | 192.168.88.104 | ✔ | software pass | ✔ | visual pass | 🔄 |
| 2 | TBD | TBD | ✗ | ✗ | ✗ | ✗ | ✗ |
| 3 | TBD | TBD | ✗ | ✗ | ✗ | ✗ | ✗ |
| 4 | TBD | TBD | ✗ | ✗ | ✗ | ✗ | ✗ |
| 5 | TBD | TBD | ✗ | ✗ | ✗ | ✗ | ✗ |

The TPA3118 control-net rework and staged amplifier test in
[AMP_TEST.md](AMP_TEST.md) are mandatory for every shield before 12 V operation.
