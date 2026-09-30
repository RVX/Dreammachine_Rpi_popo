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

## Venue network isolation (verified at OMR, 2026-09-25/26)

Many venue/visitor WiFi networks enable **AP/client isolation** — devices can
reach the router and internet but **cannot reach each other**. Verified on
OMR-VISITAS (guest network): Pi↔router ARP works, Pi↔laptop ARP fails, SSH
between LAN devices blocked.

**Solution**: Use the **equipment/staff network** instead of the guest network.
At OMR, switching from `OMR-VISITAS` (guest) to `OMR-Equipo` (equipment) solved
the isolation — the Pi and laptop can now communicate directly over WiFi.

**Diagnose from the Pi** (via the Ethernet dongle link):
```bash
ip neigh                      # laptop IP shows FAILED if isolation is on
sudo arping -c 2 -I wlan0 <gateway>   # router answers, but...
ping -c 2 <laptop-ip>         # ...laptop never replies
```

**Fix**: Add the equipment network to the Pi's network config:
```bash
sudo nmcli connection add type wifi ifname wlan0 con-name "OMR-Equipo" \
  ssid "OMR-Equipo" wifi-sec.key-mgmt wpa-psk wifi-sec.psk "team23OMR"
sudo nmcli connection up OMR-Equipo
sudo nmcli connection delete OMR-VISITAS  # remove guest network
```

### Second saved network — OMR-WIFI-5G (added 2026-09-30)

OMR IT reports `OMR-WIFI-5G` (same password `team23OMR`) as less congested/more
stable than `OMR-Equipo` — likely the same AP hardware on a separate SSID/band
(matching BSSID prefixes seen in a laptop scan). Added as a **second** saved
network rather than a replacement, so units automatically prefer it when in
range but still fall back to `OMR-Equipo` if it isn't — one less single point
of failure for units that can't be reached to fix manually:
```bash
sudo nmcli connection add type wifi ifname wlan0 con-name "OMR-WIFI-5G" \
  ssid "OMR-WIFI-5G" wifi-sec.key-mgmt wpa-psk wifi-sec.psk "team23OMR" \
  connection.autoconnect yes connection.autoconnect-priority 10
# Keep OMR-Equipo as automatic fallback (lower priority, not deleted):
sudo nmcli connection modify "OMR-Equipo" connection.autoconnect-priority 0
```
Status: deployed to dm2 only so far. Still needed on dm1/dm3/dm4/dm5 next time
each is reachable (note: dm2's profile name is `netplan-wlan0-OMR-Equipo`, not
`OMR-Equipo` — check `nmcli connection show` per host before modifying).

### Access methods by scenario

| Scenario | Method |
|---|---|
| On-site, venue LAN open | Direct via `sjcdm<N>.local` or DHCP IP |
| On-site, venue LAN isolated | Ethernet dongle (`169.254.<N>.<N>`) or Pi hotspot |
| Off-site, venue has internet | RustDesk relay or WireGuard/tunnel (below) |
| Off-site, no internet | Not possible — venue must provide some internet |

### Planned: Pi hotspot fallback (AP+STA concurrent mode)

The Pi 4 WiFi chip supports simultaneous client + AP mode: `wlan0` stays on
the venue WiFi for internet while a virtual AP interface (`wlan1`) broadcasts
`DREAMMACHINE-<N>` for direct laptop access. Both share the radio channel, so
throughput splits — fine for management. To be implemented; ask before
enabling since it changes NetworkManager setup.

### Planned: off-site access (pick one, TODO)

- **WireGuard to a VPS (preferred)** — each Pi gets a fixed tunnel IP
  (`10.0.0.N`), persistent, encrypted, self-controlled. SSH/RustDesk to the
  tunnel IP from anywhere. Needs one ~€3-5/month VPS.
- **sish** (github.com/antoniomika/sish) — open-source openport.io alternative;
  pure SSH reverse tunnels, quickest to set up.
- **rathole** / **frp** — Rust/Go tunnel daemons, more features, more config.
- **RustDesk relay** — switch from direct-IP (`direct-server Y`) to relay mode
  (`direct-server ''`) so connections work through NAT/isolation. For privacy
  on collector sites, self-host the relay (hbbs/hbbr) on the same VPS.

## Notes / caveats (cont.)
