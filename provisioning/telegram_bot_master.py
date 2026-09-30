#!/usr/bin/env python3
"""
telegram_bot_master.py — DREAMMACHINE fleet command bot (single master).

Runs ONLY on the master unit (sjcdm4). Routes commands to all units via SSH.
Prevents 409 Conflict from multiple bots polling the same token.

Commands:
  /status           -> status of ALL online units
  /statusdm<N>      -> status of specific unit (dm1-dm5)
  /update           -> update ALL units
  /updatedm<N>      -> update specific unit
  /flashdm<N>       -> flash RP2350 on specific unit
  /flsdm<N>         -> start FLS protocol on specific unit
  /flsstopdm<N>     -> stop FLS on specific unit
  /ip, /uptime      -> master unit shortcuts
  /help             -> command list
"""

import json
import subprocess
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

TELEGRAM_TOKEN = "8628742544:AAH80zdbP4OYtj0DSSDkUDj3Q9784K8cxXI"
AUTHORIZED_CHAT_ID = 350553264
API = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"

HOSTNAME = subprocess.check_output("hostname", shell=True).decode().strip()

# Fleet configuration: unit number -> (hostname, Tailscale IP, local IP fallback)
FLEET = {
    1: ("sjcdm1", "100.64.131.41", None),
    2: ("sjcdm2", "100.114.177.74", None),
    3: ("sjcdm3", "100.85.254.127", None),
    4: ("sjcdm4", "100.103.58.47", "192.168.1.77"),
    5: ("sjcdm5", "100.93.96.91", "192.168.1.203"),
}

POLL_TIMEOUT = 30
ERROR_BACKOFF_S = 10
SSH_KEY = "/home/sjc/.ssh/id_ed25519_dreammachine"


# ---------------------------------------------------------------- helpers --

def run(cmd, timeout=5):
    try:
        return subprocess.check_output(
            cmd, shell=True, stderr=subprocess.DEVNULL, timeout=timeout
        ).decode().strip()
    except Exception:
        return ""


def run_ssh(host, cmd, timeout=10):
    """Run command on remote unit via SSH, trying Tailscale then local IP."""
    # Try Tailscale first
    ts_ip = FLEET.get(host, (None, None, None))[1]
    local_ip = FLEET.get(host, (None, None, None))[2]
    
    for ip in [ts_ip, local_ip]:
        if not ip:
            continue
        try:
            full_cmd = (
                f'ssh -i {SSH_KEY} -o IdentitiesOnly=yes '
                f'-o StrictHostKeyChecking=no -o ConnectTimeout=8 '
                f'sjc@{ip} "{cmd}"'
            )
            return subprocess.check_output(
                full_cmd, shell=True, stderr=subprocess.DEVNULL, timeout=timeout
            ).decode().strip()
        except Exception:
            continue
    return ""


def api(method, **params):
    data = urllib.parse.urlencode(params).encode()
    with urllib.request.urlopen(f"{API}/{method}", data, timeout=POLL_TIMEOUT + 10) as r:
        return json.loads(r.read())


def reply(chat_id, text):
    try:
        api("sendMessage", chat_id=chat_id, text=text, parse_mode="HTML")
    except Exception as e:
        print(f"reply failed: {e}", flush=True)


# ---------------------------------------------------------------- status ---

def collect_status_local():
    """Collect status from this unit (master)."""
    now_utc = datetime.now(timezone.utc)
    now_local = now_utc.astimezone()
    try:
        now_berlin = now_utc.astimezone(ZoneInfo("Europe/Berlin"))
    except Exception:
        now_berlin = now_utc

    ts_ip = run("tailscale ip -4") or "offline"
    public_ip = run("curl -4 -s --max-time 4 ifconfig.me") or "unknown"
    wlan_ip = run("ip -4 addr show wlan0 | grep -oP 'inet \\K[\\d.]+'") or "none"
    ssid = run("nmcli -t -f NAME,DEVICE,STATE connection show --active | grep wlan0 | cut -d: -f1") or "none"
    sig = run("iwconfig wlan0 | grep -oP 'Signal level=\\K[-0-9]+ dBm'") or "?"

    led = run("systemctl is-active dreammachine-led.service") or "?"
    reaper_pid = run("pgrep -x reaper")
    reaper = f"running (pid {reaper_pid})" if reaper_pid else "not running"
    ts_state = run("systemctl is-active tailscaled") or "?"
    rustdesk_svc = run("systemctl is-active rustdesk") or "?"
    rustdesk_id = run("sudo -n -u sjc rustdesk --get-id", timeout=8) or "n/a"

    popo_last = run("tail -1 /tmp/popo_live.log 2>/dev/null | grep -oP '\\[done\\].*' | head -c 80")
    popo_wavs = run("ls /home/sjc/popo/datasets/ground/sonifications/popo_live_*.wav 2>/dev/null | wc -l") or "0"

    temp_raw = run("vcgencmd measure_temp | grep -oP '[0-9.]+'")
    temp = f"{temp_raw}C" if temp_raw else "?"
    throttled = run("vcgencmd get_throttled | cut -d= -f2")
    load = run("cut -d' ' -f1-3 /proc/loadavg")
    mem = run("free -m | awk '/^Mem:/ {print $3\"M/\"$2\"M\"}'")
    import shutil
    du = shutil.disk_usage("/")
    disk = f"{du.used // 2**30}G/{du.total // 2**30}G ({du.used * 100 // du.total}%)"
    uptime = run("uptime -p").replace("up ", "")

    last_boot = run("uptime -s")
    boot_count = run("journalctl --list-boots --no-pager 2>/dev/null | wc -l") or "?"
    prev_boot_end = run("journalctl -b -1 -n 1 --no-pager -o short-monotonic 2>/dev/null | tail -1")
    kern_errs = run("journalctl -b -p err --no-pager 2>/dev/null | wc -l") or "0"
    kern_last = run("journalctl -b -p err --no-pager -n 2 -o cat 2>/dev/null | tail -2")
    failed_units = run("systemctl --failed --no-legend --no-pager 2>/dev/null | wc -l") or "0"
    failed_list = run("systemctl --failed --no-legend --no-pager 2>/dev/null | awk '{print $1}' | head -3")

    throttled_note = ""
    if throttled and throttled != "0x0":
        flags = []
        tval = int(throttled, 16) if throttled.startswith("0x") else 0
        if tval & 0x1: flags.append("undervoltage NOW")
        if tval & 0x2: flags.append("freq-capped NOW")
        if tval & 0x4: flags.append("throttled NOW")
        if tval & 0x10000: flags.append("undervoltage occurred")
        if tval & 0x20000: flags.append("freq-cap occurred")
        if tval & 0x40000: flags.append("throttle occurred")
        throttled_note = f" ⚠️ {', '.join(flags)}" if flags else f" ⚠️ {throttled}"

    health_block = ""
    if failed_units != "0":
        health_block += f"\n⚠️ <b>Failed services ({failed_units}):</b> {failed_list}"
    if kern_errs != "0":
        last_line = kern_last.splitlines()[-1][:120] if kern_last else ""
        health_block += f"\n⚠️ <b>Kernel errors since boot ({kern_errs}):</b> {last_line}"

    return f"""📊 <b>{HOSTNAME} live status</b>

<b>Time</b>  UTC {now_utc.strftime('%H:%M')} | local {now_local.strftime('%H:%M %Z')} | Berlin {now_berlin.strftime('%H:%M')}
<b>Uptime:</b> {uptime} (booted {last_boot}, boot #{boot_count})

<b>Network</b>
WiFi: {ssid} ({wlan_ip}, {sig})
Tailscale: <code>{ts_ip}</code> | Public: {public_ip}

<b>Software</b>
LED: {led} | REAPER: {reaper}
Tailscale: {ts_state} | RustDesk: {rustdesk_svc} (ID <code>{rustdesk_id}</code>)
POPO: {popo_wavs} wavs {popo_last}

<b>Hardware</b>
CPU: {temp}{throttled_note} | load {load}
RAM: {mem} | Disk: {disk}{health_block}

<b>Access</b>  ssh sjc@{ts_ip}"""


def collect_status_remote(unit_num):
    """Collect status from a remote unit via SSH."""
    hostname = FLEET.get(unit_num, (f"sjcdm{unit_num}",))[0]
    
    # Check if unit is reachable
    check = run_ssh(unit_num, "echo ONLINE", timeout=5)
    if not check:
        return f"❌ <b>{hostname}</b> — offline/unreachable"
    
    # Get basic status
    uptime = run_ssh(unit_num, "uptime -p 2>/dev/null | sed 's/up //'", timeout=5) or "?"
    ts_ip = run_ssh(unit_num, "tailscale ip -4 2>/dev/null", timeout=5) or "offline"
    led = run_ssh(unit_num, "systemctl is-active dreammachine-led.service 2>/dev/null", timeout=5) or "?"
    reaper = run_ssh(unit_num, "pgrep -xc reaper 2>/dev/null", timeout=5)
    reaper = "running" if reaper and reaper != "0" else "not running"
    temp = run_ssh(unit_num, "vcgencmd measure_temp 2>/dev/null | grep -oP '[0-9.]+'", timeout=5) or "?"
    
    return f"""✅ <b>{hostname}</b>
  Uptime: {uptime} | Temp: {temp}C
  LED: {led} | REAPER: {reaper}
  Tailscale: <code>{ts_ip}</code>"""


def collect_status_all():
    """Collect status from all online units."""
    lines = ["📊 <b>FLEET STATUS</b>\n"]
    for unit_num in sorted(FLEET.keys()):
        lines.append(collect_status_remote(unit_num))
    return "\n\n".join(lines)


# --------------------------------------------------------------- commands --

def handle(chat_id, text):
    cmd = text.strip().lower().split()[0].lstrip("/")
    cmd = cmd.split("@")[0]  # strip @botname suffix

    # Parse unit-specific commands: /statusdm4, /updatedm5, /flsdm2, etc.
    unit_target = None
    base_cmd = cmd
    for u in FLEET.keys():
        suffix = f"dm{u}"
        if cmd.endswith(suffix):
            unit_target = u
            base_cmd = cmd[:-len(suffix)]
            break

    if base_cmd == "status":
        if unit_target:
            reply(chat_id, collect_status_remote(unit_target))
        else:
            reply(chat_id, collect_status_all())
    elif base_cmd == "uptime":
        if unit_target:
            out = run_ssh(unit_target, "uptime -p | sed 's/up //'", timeout=5)
            reply(chat_id, f"{FLEET[unit_target][0]}: up {out or '?'}")
        else:
            reply(chat_id, f"{HOSTNAME}: up {run('uptime -p').replace('up ', '')}")
    elif base_cmd == "ip":
        if unit_target:
            ts = run_ssh(unit_target, "tailscale ip -4", timeout=5) or "offline"
            wlan = run_ssh(unit_target, "ip -4 addr show wlan0 | grep -oP 'inet \\K[\\d.]+'", timeout=5) or "none"
            reply(chat_id, f"{FLEET[unit_target][0]}: tailscale <code>{ts}</code> | wifi {wlan}")
        else:
            ts_ip = run("tailscale ip -4") or "offline"
            wlan = run("ip -4 addr show wlan0 | grep -oP 'inet \\K[\\d.]+'") or "none"
            reply(chat_id, f"{HOSTNAME}: tailscale <code>{ts_ip}</code> | wifi {wlan}")
    elif base_cmd == "boots":
        if unit_target:
            out = run_ssh(unit_target, "journalctl --list-boots --no-pager 2>/dev/null | tail -5", timeout=10)
            reply(chat_id, f"<b>{FLEET[unit_target][0]}</b> recent boots:\n<code>{out or 'none'}</code>")
        else:
            boots = run("journalctl --list-boots --no-pager 2>/dev/null | tail -5")
            reply(chat_id, f"<b>{HOSTNAME}</b> recent boots:\n<code>{boots}</code>")
    elif base_cmd == "errors" or base_cmd == "logs":
        if unit_target:
            out = run_ssh(unit_target, "journalctl -b -p err --no-pager -n 8 -o cat 2>/dev/null", timeout=10)
            reply(chat_id, f"<b>{FLEET[unit_target][0]}</b> errors since boot:\n<code>{out or 'none'}</code>")
        else:
            errs = run("journalctl -b -p err --no-pager -n 8 -o cat 2>/dev/null")
            reply(chat_id, f"<b>{HOSTNAME}</b> errors since boot:\n<code>{errs or 'none'}</code>")
    elif base_cmd == "update":
        if unit_target:
            reply(chat_id, f"⏳ Updating {FLEET[unit_target][0]}...")
            out = run_ssh(unit_target, "bash /home/sjc/dm_update.sh 2>&1", timeout=120)
            lines = [l for l in out.splitlines() if l.strip()]
            result = lines[-1] if lines else "no output"
            icon = "✅" if "UPDATE-OK" in out else "⚠️"
            reply(chat_id, f"{icon} <b>{FLEET[unit_target][0]}</b>: {result}")
        else:
            # Update all units
            reply(chat_id, "⏳ Updating ALL units...")
            results = []
            for u in sorted(FLEET.keys()):
                hostname = FLEET[u][0]
                out = run_ssh(u, "bash /home/sjc/dm_update.sh 2>&1", timeout=120)
                lines = [l for l in out.splitlines() if l.strip()]
                result = lines[-1] if lines else "no output"
                icon = "✅" if "UPDATE-OK" in out else "⚠️"
                results.append(f"{icon} {hostname}: {result}")
            reply(chat_id, "\n".join(results))
    elif base_cmd == "flash":
        if unit_target:
            reply(chat_id, f"⏳ Flashing RP2350 on {FLEET[unit_target][0]}...")
            out = run_ssh(unit_target, 
                "sudo openocd -f /home/sjc/dreammachine/rp2350/rpi4-rp2350-swd.cfg "
                "-f target/rp2350.cfg "
                "-c 'program /home/sjc/dreammachine/rp2350/build/dreammachine_rp2350.elf verify reset exit' 2>&1 | tail -3",
                timeout=120)
            ok = "verified" in out.lower() or "Programming Finished" in out
            icon = "✅" if ok else "⚠️"
            reply(chat_id, f"{icon} <b>{FLEET[unit_target][0]}</b> RP2350 flash:\n<code>{out[-300:]}</code>")
        else:
            reply(chat_id, "⚠️ Specify unit: /flashdm1 through /flashdm5")
    elif base_cmd == "fls":
        if unit_target:
            out = run_ssh(unit_target,
                "/home/sjc/dreammachine/led/venv/bin/python3 /home/sjc/fls_trigger.py start",
                timeout=10)
            if "OSC-SENT" in out:
                reply(chat_id, f"⚡ FLS started on {FLEET[unit_target][0]}")
            else:
                reply(chat_id, f"⚠️ FLS failed on {FLEET[unit_target][0]} — LED controller not responding")
        else:
            reply(chat_id, "⚠️ Specify unit: /flsdm1 through /flsdm5")
    elif base_cmd == "flsstop":
        if unit_target:
            out = run_ssh(unit_target,
                "/home/sjc/dreammachine/led/venv/bin/python3 /home/sjc/fls_trigger.py stop",
                timeout=10)
            if "OSC-SENT" in out:
                reply(chat_id, f"⏹ FLS stopped on {FLEET[unit_target][0]}")
            else:
                reply(chat_id, f"⚠️ FLS stop failed on {FLEET[unit_target][0]}")
        else:
            reply(chat_id, "⚠️ Specify unit: /flsstopdm1 through /flsstopdm5")
    elif base_cmd in ("help", "start"):
        reply(chat_id, f"<b>{HOSTNAME}</b> (master) commands:\n"
                       f"/status — all units\n"
                       f"/statusdm&lt;N&gt; — unit N only\n"
                       f"/update — update ALL units\n"
                       f"/updatedm&lt;N&gt; — update unit N\n"
                       f"/flashdm&lt;N&gt; — flash RP2350 on unit N\n"
                       f"/flsdm&lt;N&gt; — start FLS on unit N\n"
                       f"/flsstopdm&lt;N&gt; — stop FLS on unit N\n"
                       f"/ip, /uptime, /boots, /errors — master only")
    else:
        pass  # ignore unknown commands silently


# ------------------------------------------------------------------ main ---

def main():
    print(f"telegram_bot_master: {HOSTNAME} polling...", flush=True)
    offset = 0
    while True:
        try:
            resp = api("getUpdates", offset=offset, timeout=POLL_TIMEOUT)
            for upd in resp.get("result", []):
                offset = upd["update_id"] + 1
                msg = upd.get("message") or {}
                chat = msg.get("chat", {})
                text = msg.get("text", "")
                if not text or chat.get("id") != AUTHORIZED_CHAT_ID:
                    continue
                print(f"cmd from {chat.get('id')}: {text}", flush=True)
                handle(chat["id"], text)
        except Exception as e:
            print(f"poll error: {e}", flush=True)
            time.sleep(ERROR_BACKOFF_S)


if __name__ == "__main__":
    main()
