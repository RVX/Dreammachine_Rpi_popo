# DREAMMACHINE Pi first-boot provisioning (cloud-init)

Templates to flash a fresh Raspberry Pi OS card so any unit `sjcdm<N>` comes
up **identifiable, remotely reachable, and remotely manageable** on the first
boot — at home, at a venue, or on a direct laptop↔Pi Ethernet cable with no
network at all.

## Files

- [user-data.template](user-data.template) — cloud-init user-data: hostname,
  `sjc` user (password `sjcsjc` + deploy SSH key pre-installed), packages,
  and a one-shot first-boot script that installs/configures RustDesk and the
  identification aids below.
- [network-config.template](network-config.template) — Ethernet DHCP with a
  static link-local fallback (`169.254.N.N/16`, N = unit number) plus WiFi
  networks (home + venue).

## What first boot sets up automatically

| Feature | Detail | Why |
|---|---|---|
| Hostname | `sjcdm<N>` | Unique per unit, shows in DHCP/mDNS |
| SSH | enabled, key + password auth | Remote shell from first boot |
| mDNS | `avahi-daemon` + SSH service file | Pi appears as `sjcdm<N>.local` and in network browsers (`dns-sd -B _ssh._tcp`) |
| SSH banner | figlet hostname + all IPs + RustDesk password on login | Instantly see which unit you're on |
| RustDesk | installed (aarch64 Debian 13), service enabled | Remote desktop |
| RustDesk password | `OMRdream<N>` (auto-derived from hostname) | Unattended access, no on-site accept click |
| RustDesk direct-IP | `direct-server Y` | Works on same LAN with no relay/account |
| Ethernet fallback | `169.254.N.N/16` static on eth0 | Direct dongle link works even with zero DHCP |

## How to provision a new card

1. Flash Raspberry Pi OS (64-bit, desktop) to the SD card with Raspberry Pi
   Imager. Do **not** use Imager's own customization if you plan to use these
   templates (they'd conflict); or use Imager customization for hostname/user/
   WiFi and skip these files entirely — pick one approach.
2. Open the card's boot partition (`bootfs`, FAT32 — Windows-readable).
3. Copy `user-data.template` → `user-data` and set `hostname: sjcdm<N>`.
   (SSH key and hashed `sjcsjc` password are already in the template.)
4. Copy `network-config.template` → `network-config` and set the static
   fallback to `169.254.<N>.<N>/16`; add the venue's WiFi under
   `access-points`.
5. Safely eject, boot the Pi, wait ~5 min (first boot expands the filesystem,
   generates SSH host keys, and downloads/installs RustDesk — needs internet).

## Connecting afterward

```powershell
$env:PATH += ";C:\Windows\System32\OpenSSH"
# Direct Ethernet dongle link (always works):
ssh -i "$env:USERPROFILE\.ssh\id_ed25519_dreammachine" -o IdentitiesOnly=yes sjc@169.254.<N>.<N>
# On a LAN with DHCP:
ssh -i "$env:USERPROFILE\.ssh\id_ed25519_dreammachine" -o IdentitiesOnly=yes sjc@sjcdm<N>.local
# Remote desktop: RustDesk client -> enter the Pi's IP -> password OMRdream<N>
```

## Notes / caveats

- RustDesk CLI config (`--password`, `--option direct-server`) is applied
  after the service's first start; if unattended access doesn't answer on the
  very first try, SSH in and run the same commands as `sjc`, then
  `systemctl restart rustdesk`.
- The one-shot script logs to `/var/log/dreammachine-firstboot.log` on the Pi
  and deletes its own systemd unit when finished.
- If the venue WiFi has a captive portal (browser login page), use the direct
  Ethernet link instead — that's what the `169.254.N.N` fallback is for.
