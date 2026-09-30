#!/usr/bin/env python3
"""
DREAMMACHINE notification script
Sends Telegram + email on boot, and (via the heartbeat timer) periodically
during the day so a silent failure doesn't go unnoticed until someone
happens to check manually. Never blocks/affects the show — best-effort,
failures are logged and swallowed.

Usage: notify.py [boot|heartbeat]  (default: boot)
"""

import re
import shutil
import smtplib
import subprocess
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from zoneinfo import ZoneInfo

# Configuration
TELEGRAM_TOKEN = "8628742544:AAH80zdbP4OYtj0DSSDkUDj3Q9784K8cxXI"
TELEGRAM_CHAT_ID = "350553264"
EMAIL_TO = "sjcvolcano@gmail.com"
EMAIL_FROM = "sjcvolcano@gmail.com"
EMAIL_PASSWORD_FILE = "/home/sjc/.email_password"  # Gmail App Password stored here


def run(cmd, timeout=5):
    """Run shell command and return output, or empty string on failure"""
    try:
        return subprocess.check_output(
            cmd, shell=True, stderr=subprocess.DEVNULL, timeout=timeout
        ).decode().strip()
    except Exception:
        return ""


def get_info():
    """Gather system information"""
    now_utc = datetime.now(timezone.utc)
    now_local = now_utc.astimezone()  # unit's configured timezone
    try:
        now_berlin = now_utc.astimezone(ZoneInfo("Europe/Berlin"))
    except Exception:
        now_berlin = now_utc

    hostname = run("hostname")
    tailscale_ip = run("tailscale ip -4") or "not connected"
    # Force IPv4 for the public IP (IPv6 is not actionable for support)
    public_ip = run("curl -4 -s --max-time 5 ifconfig.me") or "unknown"
    uptime = run("uptime -p").replace("up ", "")
    local_ip = run("ip -4 addr show wlan0 | grep -oP 'inet \\K[\\d.]+'") or "not connected"
    wifi_ssid = run("nmcli -t -f NAME,DEVICE,STATE connection show --active | grep wlan0 | cut -d: -f1") or "unknown"
    signal_dbm = run("iwconfig wlan0 | grep -oP 'Signal level=\\K[-0-9]+ dBm'") or "?"
    rustdesk_id = run("sudo -n -u sjc rustdesk --get-id", timeout=8) or "n/a"

    # Service / software health
    led_svc = run("systemctl is-active dreammachine-led.service") or "unknown"
    reaper = "running" if run("pgrep -x reaper") else "not running"
    tailscaled = run("systemctl is-active tailscaled") or "unknown"

    # Hardware health
    temp_raw = run("vcgencmd measure_temp | grep -oP '[0-9.]+'")
    temp = f"{temp_raw}C" if temp_raw else "?"
    try:
        du = shutil.disk_usage("/")
        disk = f"{du.used // 2**30}G/{du.total // 2**30}G ({du.used * 100 // du.total}%)"
    except Exception:
        disk = "?"

    return {
        "hostname": hostname,
        "tailscale_ip": tailscale_ip,
        "public_ip": public_ip,
        "uptime": uptime,
        "time_utc": now_utc.strftime("%Y-%m-%d %H:%M UTC"),
        "time_local": now_local.strftime("%Y-%m-%d %H:%M %Z"),
        "time_berlin": now_berlin.strftime("%H:%M %Z"),
        "local_ip": local_ip,
        "wifi_ssid": wifi_ssid,
        "signal_dbm": signal_dbm,
        "rustdesk_id": rustdesk_id,
        "led_svc": led_svc,
        "reaper": reaper,
        "tailscaled": tailscaled,
        "temp": temp,
        "disk": disk,
    }


def build_message(i, reason):
    """Notification text (Telegram HTML; also source for plain-text email)"""
    if reason == "heartbeat":
        title = "Heartbeat"
        icon = "⚠️" if i["reaper"] != "running" or i["led_svc"] != "active" else "💓"
    else:
        title = "Online"
        icon = "🟢"
    return f"""{icon} <b>DREAMMACHINE {title}</b>

<b>Unit:</b> {i['hostname']}  (up {i['uptime']})

<b>Time</b>
UTC: {i['time_utc']}
Unit local: {i['time_local']}
Berlin: {i['time_berlin']}

<b>Network</b>
WiFi: {i['wifi_ssid']} ({i['local_ip']}, {i['signal_dbm']})
Tailscale: <code>{i['tailscale_ip']}</code>
Public IP: {i['public_ip']}

<b>Status</b>
LED service: {i['led_svc']} | REAPER: {i['reaper']} | Tailscale: {i['tailscaled']}
CPU temp: {i['temp']} | Disk: {i['disk']}

<b>Access</b>
SSH: <code>ssh sjc@{i['tailscale_ip']}</code>
RustDesk: <code>{i['rustdesk_id']}</code>"""


def send_telegram(msg):
    try:
        data = urllib.parse.urlencode({
            "chat_id": TELEGRAM_CHAT_ID,
            "text": msg,
            "parse_mode": "HTML",
        }).encode()
        urllib.request.urlopen(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            data, timeout=10,
        )
        return True
    except Exception as e:
        print(f"Telegram failed: {e}")
        return False


def strip_html(text):
    return re.sub(r"</?(b|code)>", "", text)


def send_email(i, msg_html, reason):
    try:
        pw = open(EMAIL_PASSWORD_FILE).read().strip()
    except FileNotFoundError:
        print(f"Email password file not found: {EMAIL_PASSWORD_FILE}")
        return False

    msg = MIMEMultipart("alternative")
    title = "Heartbeat" if reason == "heartbeat" else "Online"
    msg["Subject"] = f"🟢 DREAMMACHINE {i['hostname']} {title}"
    msg["From"] = EMAIL_FROM
    msg["To"] = EMAIL_TO
    msg.attach(MIMEText(strip_html(msg_html), "plain"))

    styled = msg_html.replace("<b>", '<b style="color:#4CAF50">')
    styled = styled.replace("<code>", '<code style="background:#333;padding:1px 5px">')
    html = (
        '<html><body style="font-family:monospace;background:#1a1a2e;color:#eee;padding:20px">'
        f'<pre style="font-size:14px;color:#eee">{styled}</pre></body></html>'
    )
    msg.attach(MIMEText(html, "html"))

    for port, use_ssl in ((587, False), (465, True)):
        try:
            if use_ssl:
                server = smtplib.SMTP_SSL("smtp.gmail.com", port, timeout=15)
            else:
                server = smtplib.SMTP("smtp.gmail.com", port, timeout=15)
                server.starttls()
            with server:
                server.login(EMAIL_FROM, pw)
                server.sendmail(EMAIL_FROM, EMAIL_TO, msg.as_string())
            return True
        except Exception as e:
            print(f"Email port {port} failed: {e}")
    return False


def log(msg):
    for path in ("/var/log/dreammachine-notify.log", "/home/sjc/notify.log"):
        try:
            with open(path, "a") as f:
                f.write(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} {msg}\n")
            return
        except PermissionError:
            continue


if __name__ == "__main__":
    reason = sys.argv[1] if len(sys.argv) > 1 else "boot"
    info = get_info()
    # Heartbeat is opportunistic-only: if Telegram is unreachable (no
    # internet), just skip silently rather than retrying — it must never
    # compete for resources with, or delay, anything show-critical.
    message = build_message(info, reason)
    tg = send_telegram(message)
    em = send_email(info, message, reason)
    status = f"Notification ({reason}) for {info['hostname']}: Telegram={'OK' if tg else 'FAIL'} Email={'OK' if em else 'FAIL'}"
    log(status)
    print(status)
