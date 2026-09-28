#!/usr/bin/env python3
"""
telegram_bot.py — DREAMMACHINE Telegram command bot.

Long-polls the Telegram Bot API and answers commands from the authorized
chat only:

  /status           -> real-time status of THIS unit
  /status<hostname> -> same, but only answers if it matches this unit
                       (e.g. /statusdm4, /statusdm2) so each unit in a
                       group/fleet answers only its own command
  /uptime, /ip      -> quick shortcuts
  /help             -> command list

Runs as the telegram-bot.service systemd unit (Restart=always).
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
# short alias: sjcdm4 -> dm4
ALIAS = HOSTNAME.replace("sjc", "")

POLL_TIMEOUT = 30          # long-poll seconds
ERROR_BACKOFF_S = 10


# ---------------------------------------------------------------- helpers --

def run(cmd, timeout=5):
    try:
        return subprocess.check_output(
            cmd, shell=True, stderr=subprocess.DEVNULL, timeout=timeout
        ).decode().strip()
    except Exception:
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

def collect_status():
    now_utc = datetime.now(timezone.utc)
    now_local = now_utc.astimezone()
    try:
        now_berlin = now_utc.astimezone(ZoneInfo("Europe/Berlin"))
    except Exception:
        now_berlin = now_utc

    # network
    ts_ip = run("tailscale ip -4") or "offline"
    public_ip = run("curl -4 -s --max-time 4 ifconfig.me") or "unknown"
    wlan_ip = run("ip -4 addr show wlan0 | grep -oP 'inet \\K[\\d.]+'") or "none"
    ssid = run("nmcli -t -f NAME,DEVICE,STATE connection show --active | grep wlan0 | cut -d: -f1") or "none"
    sig = run("iwconfig wlan0 | grep -oP 'Signal level=\\K[-0-9]+ dBm'") or "?"

    # software
    led = run("systemctl is-active dreammachine-led.service") or "?"
    reaper_pid = run("pgrep -x reaper")
    reaper = f"running (pid {reaper_pid})" if reaper_pid else "not running"
    ts_state = run("systemctl is-active tailscaled") or "?"
    rustdesk_svc = run("systemctl is-active rustdesk") or "?"
    rustdesk_id = run("sudo -n -u sjc rustdesk --get-id", timeout=8) or "n/a"

    # POPO sonification: last run time from log
    popo_last = run("tail -1 /tmp/popo_live.log 2>/dev/null | grep -oP '\[done\].*' | head -c 80")
    popo_wavs = run("ls /home/sjc/popo/datasets/ground/sonifications/popo_live_*.wav 2>/dev/null | wc -l") or "0"

    # hardware
    temp_raw = run("vcgencmd measure_temp | grep -oP '[0-9.]+'")
    temp = f"{temp_raw}C" if temp_raw else "?"
    throttled = run("vcgencmd get_throttled | cut -d= -f2")
    load = run("cut -d' ' -f1-3 /proc/loadavg")
    mem = run("free -m | awk '/^Mem:/ {print $3\"M/\"$2\"M\"}'")
    import shutil
    du = shutil.disk_usage("/")
    disk = f"{du.used // 2**30}G/{du.total // 2**30}G ({du.used * 100 // du.total}%)"
    uptime = run("uptime -p").replace("up ", "")

    # --- crash / reboot diagnostics ---
    last_boot = run("uptime -s")
    # number of recorded boots in the journal; >1 with short uptime = recent reboot
    boot_count = run("journalctl --list-boots --no-pager 2>/dev/null | wc -l") or "?"
    # previous boot: unexpected power loss / watchdog / panic shows as unclean shutdown
    prev_boot_end = run("journalctl -b -1 -n 1 --no-pager -o short-monotonic 2>/dev/null | tail -1")
    # kernel errors/warnings since this boot (OOM killer, undervoltage, fs errors)
    kern_errs = run("journalctl -b -p err --no-pager 2>/dev/null | wc -l") or "0"
    kern_last = run("journalctl -b -p err --no-pager -n 2 -o cat 2>/dev/null | tail -2")
    # failed systemd units right now
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


# --------------------------------------------------------------- commands --

def handle(chat_id, text):
    cmd = text.strip().lower().split()[0].lstrip("/")
    cmd = cmd.split("@")[0]  # strip @botname suffix

    if cmd in ("status", f"status{ALIAS}"):
        reply(chat_id, collect_status())
    elif cmd.startswith("status"):
        pass  # /statusdm2 etc. for other units — stay silent
    elif cmd == "uptime":
        reply(chat_id, f"{HOSTNAME}: up {run('uptime -p').replace('up ', '')}")
    elif cmd == "ip":
        ts_ip = run("tailscale ip -4") or "offline"
        wlan = run("ip -4 addr show wlan0 | grep -oP 'inet \\K[\\d.]+'") or "none"
        reply(chat_id, f"{HOSTNAME}: tailscale <code>{ts_ip}</code> | wifi {wlan}")
    elif cmd in ("boots", "reboots"):
        boots = run("journalctl --list-boots --no-pager 2>/dev/null | tail -5")
        reply(chat_id, f"<b>{HOSTNAME}</b> recent boots:\n<code>{boots}</code>")
    elif cmd == "fls" or cmd == f"fls{ALIAS}":
        # Send OSC /fls/start to the LED controller via the helper script
        # (avoids shell-quoting pitfalls of a python -c one-liner)
        out = run("/home/sjc/dreammachine/led/venv/bin/python3 /home/sjc/fls_trigger.py start",
                  timeout=10)
        if "OSC-SENT" in out:
            reply(chat_id, "⚡ FLS 60-min stroboscopic protocol STARTED on AMOS1+2 (in sync).")
        else:
            reply(chat_id, "⚠️ FLS trigger failed — LED controller not responding on OSC :9000")
    elif cmd == "flsstop" or cmd == f"flsstop{ALIAS}":
        out = run("/home/sjc/dreammachine/led/venv/bin/python3 /home/sjc/fls_trigger.py stop",
                  timeout=10)
        if "OSC-SENT" in out:
            reply(chat_id, "⏹ FLS protocol stopped — back to ambient mode.")
        else:
            reply(chat_id, "⚠️ FLS stop failed — LED controller not responding on OSC :9000")
    elif cmd == "update" or cmd == f"update{ALIAS}":
        reply(chat_id, "⏳ Pulling latest code...")
        out = run("bash /home/sjc/dm_update.sh 2>&1", timeout=120)
        # result line is the last non-empty line (git prints noise before it)
        result = [l for l in out.splitlines() if l.strip()][-1] if out.strip() else "no output"
        icon = "✅" if "UPDATE-OK" in out else "⚠️"
        reply(chat_id, f"{icon} <b>{HOSTNAME}</b>: {result}")
    elif cmd.startswith("update"):
        pass  # /updatedm2 etc. for other units — stay silent
    elif cmd == "flash" or cmd == f"flash{ALIAS}":
        reply(chat_id, "⏳ Flashing RP2350 firmware... (LEDs will freeze ~10s)")
        out = run("sudo openocd -f /home/sjc/dreammachine/rp2350/rpi4-rp2350-swd.cfg "
                  "-f target/rp2350.cfg "
                  "-c 'program /home/sjc/dreammachine/rp2350/build/dreammachine_rp2350.elf verify reset exit' 2>&1 "
                  "| tail -3", timeout=120)
        ok = "verified" in out.lower() or "Programming Finished" in out
        icon = "✅" if ok else "⚠️"
        reply(chat_id, f"{icon} <b>{HOSTNAME}</b> RP2350 flash:\n<code>{out[-300:]}</code>")
    elif cmd in ("errors", "logs"):
        errs = run("journalctl -b -p err --no-pager -n 8 -o cat 2>/dev/null")
        reply(chat_id, f"<b>{HOSTNAME}</b> errors since boot:\n<code>{errs or 'none'}</code>")
    elif cmd in ("help", "start"):
        reply(chat_id, f"<b>{HOSTNAME}</b> commands:\n"
                       f"/status — full live status\n"
                       f"/status{ALIAS} — this unit only\n"
                       f"/uptime — uptime\n"
                       f"/ip — IP addresses\n"
                       f"/boots — recent boot history\n"
                       f"/errors — kernel/service errors since boot\n"
                       f"/update — update ALL units\n"
                       f"/update{ALIAS} — update this unit only\n"
                       f"/flash — flash RP2350 firmware from repo")
    else:
        pass  # ignore unknown commands silently


# ------------------------------------------------------------------ main ---

def main():
    print(f"telegram_bot: {HOSTNAME} (alias {ALIAS}) polling...", flush=True)
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
