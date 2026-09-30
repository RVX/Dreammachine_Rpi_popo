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

## Reliability architecture: the show must never stop (added 2026-10-01)

**Top priority for this installation**: REAPER audio + LEDs run continuously
9:45-23:00 daily. Network/internet availability is explicitly secondary — if
there is no internet, the show must keep playing exactly the same. Silence
or dark LEDs is the worst-case outcome, worse than losing remote access.

This means: **nothing that exists only to fix a network problem is allowed
to interrupt the show.** Concretely, `network_watchdog.sh`'s last-resort
reboot (previously triggered purely by sustained network loss) now checks
`show_is_healthy()` (REAPER process running + `dreammachine-led.service`
active) first, and refuses to reboot a unit whose show is fine — it just
keeps retrying NetworkManager instead, indefinitely.

Two independent watchdogs, installed together by `install_wifi_setup.sh`:

- **[network_watchdog.sh](network_watchdog.sh) / `network-watchdog.service`**
  — recovers a hung network stack (NetworkManager restart, then reboot —
  but only if the show is also down). Doesn't care about REAPER/LEDs unless
  deciding whether a reboot is safe.
- **[show_watchdog.sh](show_watchdog.sh) / `show-watchdog.service`** (new)
  — recovers a hung/dead REAPER. lxsession's `@`-prefix autostart
  (`systemd/rpd-x-autostart`) already restarts `start_reaper.sh` if it
  *exits*, but that mechanism can't catch an **Xorg hang** (X11 still
  "running" but wedged — observed in the field on dm3). This watchdog
  detects `reaper` not running for ~3 min and automates the known-good
  manual fix from [debug_autostart.sh](debug_autostart.sh)
  (`systemctl restart lightdm`), and only reboots if that doesn't bring
  REAPER back after a couple of tries.

Both watchdogs log to `/var/log/dreammachine-*-watchdog.log` and wrap every
external call in `timeout` so a watchdog can't itself hang.

**Still open / not yet implemented** (see project plan): RP2350 firmware
amp-unmute hardening (continuous retry / status readback instead of a
one-shot 300ms window), UPS/battery buffering, and physical/electrical
investigation of dm4's fuse issue (deferred — not realistic to improve this
hardware at the moment).

### Fleet monitoring: Telegram + email (added 2026-10-01, was dm4-only prototype)

Installed by [install_monitoring.sh](install_monitoring.sh) — now tracked
under [monitoring/](monitoring/) instead of living only as a one-off on dm4:

- **Boot notification** (`notify-boot.service` → `notify.py`) — Telegram +
  email on every boot with hostname, uptime, WiFi/Tailscale/public IP, LED
  service + REAPER status, temp, disk.
- **On-demand Telegram bot** (`telegram-bot.service` → `telegram_bot.py`,
  `Restart=always`) — `/status`, `/statusdm<N>`, `/uptime`, `/ip`, `/boots`,
  `/errors`, `/update` (git pull + restart services), `/flash` (reflash
  RP2350 firmware), `/help`. Each unit only answers its own
  `/status<alias>`/`/update<alias>` commands so a group chat with the whole
  fleet works without cross-talk.
- **Periodic heartbeat** (`dreammachine-heartbeat.timer`, new) — same
  message as boot notification but at 10:00/14:00/18:00/22:00 daily, so a
  silent mid-day failure (REAPER crashed but Pi stayed up) is caught within
  a few hours instead of only at the next reboot. Best-effort/opportunistic
  only — if there's no internet it just fails silently and retries next
  cycle, never touches the show.
- Needs `/home/sjc/.email_password` (Gmail App Password) per unit for email
  delivery — not tracked in git, copy manually. Telegram works without it.

### Show-hours gating + nightly maintenance reboot (added 2026-10-01)

Installed by [install_show_hours.sh](install_show_hours.sh):

- **09:45 daily** — `dreammachine-show-open.timer` runs
  [show_hours_gate.sh](show_hours_gate.sh) `open`: starts
  `dreammachine-led.service` and unmutes the amp.
- **23:00 daily** — `dreammachine-show-close.timer` runs the same script
  `close`: mutes the amp and stops `dreammachine-led.service`.
- **REAPER itself is never stopped or restarted** by this gating — it keeps
  its tracks looping quietly in the background the whole time. Only the amp
  and LED output are gated. This avoids the reliability/SD-corruption risk
  of power-cycling or restarting the audio engine daily.
- **03:00 daily** (well inside the closed window) —
  `dreammachine-nightly-reboot.timer` does a full `reboot`. This exists
  because the fleet runs unattended for months (currently Mexico City, with
  no guarantee of on-site or remote access at any given moment) — a nightly
  reboot during closed hours gives a guaranteed, zero-visitor-risk way to
  clear any slow memory/X11/log drift, instead of depending on someone being
  able to remote in to reboot manually. No `Persistent=true` on this one on
  purpose — if it's missed one night, better to skip it than have it fire
  late during show hours.
- **Timezone-dependent**: `OnCalendar` uses the Pi's local system timezone.
  Verify with `timedatectl` on each unit before relying on this; set with
  `sudo timedatectl set-timezone America/Mexico_City` if wrong.
- Interaction with the watchdogs above: `dreammachine-led.service` is
  intentionally stopped 23:00-09:45, so `network_watchdog.sh`'s
  `show_is_healthy()` check will report "unhealthy" overnight — that's
  expected and harmless (no visitor impact, and any resulting reboot is just
  a bonus maintenance reboot).

