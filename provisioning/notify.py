#!/usr/bin/env python3
"""
DREAMMACHINE notification script
Sends Telegram + email when a Pi joins the Tailnet or boots
"""

import subprocess
import smtplib
import urllib.request
import urllib.parse
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime

# Configuration
TELEGRAM_TOKEN = "8628742544:AAH80zdbP4OYtj0DSSDkUDj3Q9784K8cxXI"
TELEGRAM_CHAT_ID = "350553264"
EMAIL_TO = "sjcvolcano@gmail.com"
EMAIL_FROM = "sjcvolcano@gmail.com"
EMAIL_PASSWORD_FILE = "/home/sjc/.email_password"  # Gmail App Password stored here

def run(cmd):
    """Run shell command and return output"""
    try:
        return subprocess.check_output(cmd, shell=True, stderr=subprocess.DEVNULL, timeout=5).decode().strip()
    except:
        return "unknown"

def get_info():
    """Gather system information"""
    hostname = run("hostname")
    tailscale_ip = run("tailscale ip -4") or "not connected"
    public_ip = run("curl -s --max-time 5 ifconfig.me") or "unknown"
    uptime = run("uptime -p").replace("up ", "")
    timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
    local_ip = run("ip -4 addr show wlan0 | grep -oP 'inet \\K[\\d.]+'") or "not connected"
    wifi_ssid = run("nmcli -t -f NAME,DEVICE,STATE connection show --active | grep wlan0 | cut -d: -f1") or "unknown"
    rustdesk_id = run("sudo -u sjc rustdesk --get-id") or "not installed"
    
    return {
        "hostname": hostname,
        "tailscale_ip": tailscale_ip,
        "public_ip": public_ip,
        "uptime": uptime,
        "timestamp": timestamp,
        "local_ip": local_ip,
        "wifi_ssid": wifi_ssid,
        "rustdesk_id": rustdesk_id,
    }

def send_telegram(info):
    """Send Telegram notification"""
    message = f"""🟢 <b>DREAMMACHINE Unit Online</b>

<b>Unit:</b> {info['hostname']}
<b>Tailscale IP:</b> {info['tailscale_ip']}
<b>Local Network:</b> {info['wifi_ssid']} ({info['local_ip']})
<b>Public IP:</b> {info['public_ip']}
<b>Uptime:</b> {info['uptime']}
<b>Time:</b> {info['timestamp']}

<b>Access:</b>
SSH: <code>ssh sjc@{info['tailscale_ip']}</code>
RustDesk ID: <code>{info['rustdesk_id']}</code>"""
    
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    data = urllib.parse.urlencode({
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "HTML"
    }).encode()
    
    try:
        urllib.request.urlopen(url, data, timeout=10)
        return True
    except Exception as e:
        print(f"Telegram failed: {e}")
        return False

def send_email(info):
    """Send email notification via Gmail SMTP"""
    try:
        with open(EMAIL_PASSWORD_FILE, "r") as f:
            password = f.read().strip()
    except FileNotFoundError:
        print(f"Email password file not found: {EMAIL_PASSWORD_FILE}")
        return False
    
    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"🟢 DREAMMACHINE {info['hostname']} Online"
    msg["From"] = EMAIL_FROM
    msg["To"] = EMAIL_TO
    
    text = f"""DREAMMACHINE Unit Online

Unit: {info['hostname']}
Tailscale IP: {info['tailscale_ip']}
Local Network: {info['wifi_ssid']} ({info['local_ip']})
Public IP: {info['public_ip']}
Uptime: {info['uptime']}
Time: {info['timestamp']}

Access:
SSH: ssh sjc@{info['tailscale_ip']}
RustDesk ID: {info['rustdesk_id']}
"""
    
    html = f"""<html><body style="font-family: monospace; background: #1a1a2e; color: #eee; padding: 20px;">
<h2 style="color: #4CAF50;">🟢 DREAMMACHINE Unit Online</h2>
<table style="border-collapse: collapse;">
<tr><td style="padding: 5px; color: #888;">Unit:</td><td style="padding: 5px;"><b>{info['hostname']}</b></td></tr>
<tr><td style="padding: 5px; color: #888;">Tailscale IP:</td><td style="padding: 5px;"><code>{info['tailscale_ip']}</code></td></tr>
<tr><td style="padding: 5px; color: #888;">Local Network:</td><td style="padding: 5px;">{info['wifi_ssid']} ({info['local_ip']})</td></tr>
<tr><td style="padding: 5px; color: #888;">Public IP:</td><td style="padding: 5px;">{info['public_ip']}</td></tr>
<tr><td style="padding: 5px; color: #888;">Uptime:</td><td style="padding: 5px;">{info['uptime']}</td></tr>
<tr><td style="padding: 5px; color: #888;">Time:</td><td style="padding: 5px;">{info['timestamp']}</td></tr>
</table>
<h3 style="color: #888;">Access:</h3>
<p>SSH: <code style="background: #333; padding: 3px 8px;">ssh sjc@{info['tailscale_ip']}</code></p>
<p>RustDesk ID: <code style="background: #333; padding: 3px 8px;">{info['rustdesk_id']}</code></p>
</body></html>"""
    
    msg.attach(MIMEText(text, "plain"))
    msg.attach(MIMEText(html, "html"))
    
    try:
        # Try port 587 with STARTTLS first (more reliable from datacenter IPs)
        with smtplib.SMTP("smtp.gmail.com", 587, timeout=15) as server:
            server.starttls()
            server.login(EMAIL_FROM, password)
            server.sendmail(EMAIL_FROM, EMAIL_TO, msg.as_string())
        return True
    except Exception as e:
        print(f"Email 587 failed: {e}, trying 465...")
        
    try:
        # Fallback to port 465 with SSL
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=15) as server:
            server.login(EMAIL_FROM, password)
            server.sendmail(EMAIL_FROM, EMAIL_TO, msg.as_string())
        return True
    except Exception as e:
        print(f"Email 465 also failed: {e}")
        return False

def log(msg):
    """Log to file"""
    try:
        with open("/var/log/dreammachine-notify.log", "a") as f:
            f.write(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} {msg}\n")
    except PermissionError:
        # Fall back to user log
        with open("/home/sjc/notify.log", "a") as f:
            f.write(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} {msg}\n")

if __name__ == "__main__":
    info = get_info()
    
    telegram_ok = send_telegram(info)
    email_ok = send_email(info)
    
    status = f"Telegram={'OK' if telegram_ok else 'FAIL'} Email={'OK' if email_ok else 'FAIL'}"
    log(f"Notification for {info['hostname']}: {status}")
    print(status)
