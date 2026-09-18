# Migration — cloning the verified sjcdm1 build to Pi 2-5

> **12 V HOLD FOR ALL FIVE SHIELDS:** Complete the R78/R79/R81 control rework
> and C65/C67 input rework in [AMP_TEST.md](AMP_TEST.md) before any external
> 12 V test. Also connect PCM5102A `XSMT` to `+3.3VDAC` as documented in
> [DAC_TEST.md](DAC_TEST.md). These corrections cannot be replaced by firmware.

Once `sjcdm1` is fully tested end-to-end (audio via Audio+ shield, LED sync
via OSC, kiosk autostart, VNC access), replicate it to the remaining 4 Pis.

Two options — pick based on time available on site vs. remotely:

## Option A — SD card image clone (verified procedure, cloud-init based)

`sjcdm1` runs a Raspberry Pi Imager cloud-init image (`/boot/user-data` +
`network-config`), not stock `raspi-config` first-boot. Hostname, SSH host
keys, and machine-id must be reset through that seed, not `raspi-config`.
Executed and verified once already (sjcdm1 -> sjcdm2, 2026-09-18).

1. Shut down `sjcdm1`: `sudo shutdown now`. Remove its SD card and insert it
   into a USB card reader.
2. Identify the device node before touching anything. Never assume; confirm
   size and partition layout every time:
   ```sh
   lsblk -o NAME,SIZE,TYPE,TRAN,MOUNTPOINT,FSTYPE,LABEL
   ```
   The source card shows a `bootfs` (vfat, ~512M) and `rootfs` (ext4,
   remainder) partition pair. Note its device, e.g. `/dev/sdb`.
3. Unmount any auto-mounted source partitions, then create a compressed
   master image (read-only against the source card):
   ```sh
   udisksctl unmount -b /dev/sdb1   # repeat per auto-mounted partition
   sudo dd if=/dev/sdb bs=4M status=progress \
     | gzip -c > ~/Desktop/dreammachine_master.img.gz
   gzip -t ~/Desktop/dreammachine_master.img.gz   # must print nothing / exit 0
   ```
4. Swap cards: remove the source, insert a blank destination card (a second
   USB reader is easiest so both can be in at once). Re-run `lsblk` and
   confirm the *new* device node — do not reuse the source's node from step 2.
5. Unmount the destination's auto-mounted partition(s), then write the full
   image to the **whole disk device**, never to a partition (`/dev/sdc`, not
   `/dev/sdc1`):
   ```sh
   udisksctl unmount -b /dev/sdc1
   gunzip -c ~/Desktop/dreammachine_master.img.gz \
     | sudo dd of=/dev/sdc bs=4M status=progress conv=fsync
   sync
   lsblk -o NAME,SIZE,FSTYPE,LABEL /dev/sdc   # confirm bootfs/rootfs match source
   ```
6. Rename the clone's identity before it ever boots. Mount both partitions,
   then edit rootfs and the boot-partition cloud-init seed together:
   ```sh
   udisksctl mount -b /dev/sdc2   # -> /run/media/$USER/rootfs
   udisksctl mount -b /dev/sdc1   # -> /run/media/$USER/bootfs
   ROOT=/run/media/$USER/rootfs
   BOOT=/run/media/$USER/bootfs
   NEWNAME=sjcdm2   # increment per unit: sjcdm3, sjcdm4, sjcdm5

   sudo bash -c "
     echo $NEWNAME > '$ROOT/etc/hostname'
     sed -i 's/\bsjcdm1\b/$NEWNAME/g' '$ROOT/etc/hosts'
     sed -i 's/\bsjcdm1\b/$NEWNAME/g' '$BOOT/user-data'
     rm -f '$ROOT'/etc/ssh/ssh_host_*
     truncate -s 0 '$ROOT/etc/machine-id'
     rm -rf '$ROOT'/var/lib/cloud/instances/* '$ROOT'/var/lib/cloud/data/*
     rm -f '$ROOT'/var/log/cloud-init*.log
   "
   ```
   - `/boot/user-data` (the Raspberry Pi Imager cloud-init seed) has its own
     `hostname: sjcdm1` line. If this is not also updated, resetting the
     cloud-init instance state below makes cloud-init re-apply the *old* name
     from the seed on first boot, undoing the `/etc/hostname` edit.
   - Removing `ssh_host_*` and truncating `machine-id` to 0 bytes makes
     systemd/openssh regenerate unique values on first boot.
   - Clearing `/var/lib/cloud/instances` and `/var/lib/cloud/data` makes
     cloud-init treat the card as a brand-new instance and fully re-run the
     (now-corrected) seed, instead of skipping steps it thinks already ran.
7. Verify before ejecting:
   ```sh
   cat "$ROOT/etc/hostname"                 # -> sjcdm2
   grep sjcdm2 "$ROOT/etc/hosts"
   grep hostname "$BOOT/user-data"          # -> hostname: sjcdm2
   stat -c%s "$ROOT/etc/machine-id"         # -> 0
   ls "$ROOT"/etc/ssh/ssh_host_* 2>/dev/null   # -> nothing
   ```
8. Unmount and power off before removing the card:
   ```sh
   udisksctl unmount -b /dev/sdc1
   udisksctl unmount -b /dev/sdc2
   udisksctl power-off -b /dev/sdc
   ```
9. Boot the target Pi with this card. First boot regenerates SSH host keys
   and machine-id, and cloud-init re-applies the corrected hostname and
   network-config. Confirm with `ping sjcdm2.local` (avahi) or the router's
   DHCP table, then continue the per-unit checklist:
   - Flash the RP2350B over SWD and run the SPI bounce test
     ([RP2350.md](RP2350.md)).
   - Confirm `aplay -l` shows `sndrpihifiberry` and run the DAC test
     ([DAC_TEST.md](DAC_TEST.md)).
   - Confirm the R78/R79/R81 and C65 rework status for that physical shield
     before any 12 V test ([AMP_TEST.md](AMP_TEST.md)) — cloning the SD card
     does not change or verify the shield's hardware rework state.
   - If REAPER's evaluation/license is per-machine, re-enter the license (see
     REAPER > Help > About REAPER).

### Verify every destination card first: fake/counterfeit capacity risk

During units 3/4 provisioning (2026-09-18), one blank card reported
58.3G in `lsblk` and accepted a partition table, but `dd` failed with
`No space left on device` after only ~1.6 GB written. `f3probe` showed its
*real* usable size was **0 bytes** despite announcing 58.3 GB — a fake/dead
card. `lsblk`/`fdisk` cannot detect this; they only report what the card's
firmware claims. Install `f3` (`sudo pacman -S f3` on Manjaro, `apt install
f3` on Debian/Ubuntu) and test every blank card before writing to it:

```sh
sudo f3probe --destructive --time-ops /dev/sdX
```

`f3probe` is itself destructive (it overwrites the card while testing), so
run it only on the intended destination, then write the image immediately
after a pass. "Usable size" must equal "Announced size" for the card to be
trustworthy; anything less means discard the card.

Separately, the same session hit a `dd` failure on a card that `f3probe` had
just confirmed genuine, with kernel logs (`sudo dmesg`) showing the entire
USB hub disconnect/reconnect mid-write. That was a USB bus power brownout
(the reader was sharing a hub with other devices), not a bad card — simply
retrying the `dd` write on the same, already-verified card succeeded. If a
write fails, check `sudo dmesg | tail -60` for a hub disconnect before
assuming the card is bad; re-run `f3probe` only if genuinely unsure.

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
| 2 | sjcdm2 | TBD | 🔄 regenerates on first boot | ✗ | ✗ | ✗ | ✗ |
| 3 | sjcdm3 | TBD | 🔄 regenerates on first boot | ✗ | ✗ | ✗ | ✗ |
| 4 | sjcdm4 | TBD | 🔄 regenerates on first boot | ✗ | ✗ | ✗ | ✗ |
| 5 | TBD | TBD | ✗ | ✗ | ✗ | ✗ | ✗ |

Units 2-4: SD cards cloned from `sjcdm1` and renamed per Option A
(2026-09-18). None installed/booted in their target Pi yet — every column
past hostname is still outstanding until first boot and the per-unit
checklist above. One blank card intended for this batch was discarded as a
confirmed fake (0 bytes usable via `f3probe`); see the fake-card note above.


The TPA3118 control-net rework and staged amplifier test in
[AMP_TEST.md](AMP_TEST.md) are mandatory for every shield before 12 V operation.
