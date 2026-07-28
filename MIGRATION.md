# Migration — cloning the verified sjcdm1 build to Pi 2-5

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
   - Confirm the Audio+ shield is detected: `aplay -l` should show
     `sndrpihifiberry` — no config changes should be needed (EEPROM auto-detect).

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
audio comes out the shield, LED service is `active (running)`
(`systemctl status dreammachine-led.service`), and VNC is reachable.

## Fleet tracking

| Pi | Hostname | IP | SSH key installed | REAPER+OSC configured | LED service verified |
|---|---|---|---|---|---|
| 1 (reference) | sjcdm1 | 192.168.88.104 | ✔ | 🔄 in progress | 🔄 in progress |
| 2 | TBD | TBD | ✗ | ✗ | ✗ |
| 3 | TBD | TBD | ✗ | ✗ | ✗ |
| 4 | TBD | TBD | ✗ | ✗ | ✗ |
| 5 | TBD | TBD | ✗ | ✗ | ✗ |
