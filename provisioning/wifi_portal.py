#!/usr/bin/env python3
"""
DREAMMACHINE WiFi Setup Portal
Runs when no known WiFi is available. Creates hotspot + web config page.
"""
import json
import logging
import subprocess
import threading
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import parse_qs, urlparse

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(message)s')
log = logging.getLogger(__name__)

HOTSPOT_SSID = None  # Set from hostname
HOTSPOT_IP = "10.42.0.1"  # NetworkManager's default hotspot IP
CONFIG_FILE = Path("/home/sjc/.wifi_configured")

HTML_PAGE = """<!DOCTYPE html>
<html>
<head>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>DREAMMACHINE — WiFi Setup</title>
    <style>
        * { box-sizing: border-box; }
        body { font-family: -apple-system, 'Helvetica Neue', sans-serif; margin: 0; background: #000; color: #fff; min-height: 100vh; }
        .hero { width: 100%; max-height: 40vh; object-fit: cover; display: block; }
        .content { max-width: 480px; margin: 0 auto; padding: 24px 20px 40px; }
        h1 { font-size: 22px; font-weight: 300; letter-spacing: 4px; margin: 0 0 8px; }
        p.sub { color: #888; font-size: 14px; margin: 0 0 24px; }
        label { display: block; font-size: 13px; color: #aaa; margin: 16px 0 6px; text-transform: uppercase; letter-spacing: 1px; }
        select, input { width: 100%; padding: 14px; border: 1px solid #333; border-radius: 6px; background: #111; color: #fff; font-size: 16px; }
        button { width: 100%; padding: 16px; margin-top: 24px; border: none; border-radius: 6px; background: #fff; color: #000; font-size: 16px; font-weight: 600; cursor: pointer; }
        button:active { background: #ccc; }
        .status { padding: 16px; margin-top: 20px; border-radius: 6px; display: none; font-size: 15px; line-height: 1.5; }
        .success { background: #0a3d0a; border: 1px solid #2d5a2d; }
        .error { background: #3d0a0a; border: 1px solid #5a2d2d; }
        .info { background: #0a1e3d; border: 1px solid #2d3d5a; }
        .diag { margin-top: 16px; padding: 12px; background: #111; border-radius: 6px; font-family: monospace; font-size: 12px; color: #888; display: none; }
        .diag.show { display: block; }
    </style>
</head>
<body>
    <img class="hero" src="/header.jpg" alt="Dark Labyrinth">
    <div class="content">
        <h1>DARK LABYRINTH</h1>
        <p class="sub">UNIT_ID &mdash; WiFi setup</p>
        <form id="wifiForm">
            <label>WiFi Network</label>
            <select id="ssid" name="ssid" required>
                <option value="">Scanning...</option>
            </select>
            <label>Password</label>
            <input type="password" id="password" name="password" placeholder="Network password">
            <button type="submit">Connect</button>
        </form>
        <div id="status" class="status"></div>
        <div id="diag" class="diag"></div>
    </div>
    <script>
        const UNIT = 'UNIT_ID';
        fetch('/scan').then(r => r.json()).then(data => {
            const select = document.getElementById('ssid');
            select.innerHTML = '<option value="">Select network...</option>';
            data.networks.forEach(net => {
                const opt = document.createElement('option');
                opt.value = net.ssid;
                opt.textContent = net.ssid + ' (' + net.signal + '%)';
                select.appendChild(opt);
            });
        });
        document.getElementById('wifiForm').onsubmit = async (e) => {
            e.preventDefault();
            const status = document.getElementById('status');
            const diag = document.getElementById('diag');
            const ssid = document.getElementById('ssid').value;
            status.style.display = 'block';
            status.className = 'status info';
            status.innerHTML = 'Connecting to <b>' + ssid + '</b>...<br>This setup network (SJCDM4-SETUP) will disappear.<br>Reconnect your phone to your normal WiFi.';
            try {
                const res = await fetch('/connect', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/x-www-form-urlencoded'},
                    body: 'ssid=' + encodeURIComponent(ssid) + '&password=' + encodeURIComponent(document.getElementById('password').value)
                });
                const data = await res.json();
                status.className = 'status success';
                status.innerHTML = '<b>The setup of the DREAMMACHINE is now complete.</b><br><br>This artwork is now joining: <b>' + ssid + '</b><br><br>Please close this page and come back in case you bring it to a new location or your WiFi changes.';
                diag.className = 'diag show';
                const diagText = 'Unit: ' + data.unit + '\n' +
                    'Network: ' + ssid + '\n' +
                    'Ref ID: ' + data.ref + '\n' +
                    'Time: ' + new Date().toISOString().replace('T', ' ').substring(0, 19) + ' UTC\n' +
                    'Uptime: ' + data.uptime + '\n' +
                    'Ethernet IP: ' + data.eth0_ip + '\n' +
                    'RustDesk ID: ' + data.rustdesk_id + '\n' +
                    'WiFi Signal: ' + data.wifi_signal;
                diag.innerHTML = '<b>Info to be sent to Studio Charrière (Berlin headquarters):</b><br><br>' +
                    '<div style="background:#000;padding:12px;border-radius:4px;font-size:11px;line-height:1.6;">' +
                    diagText.replace(/\n/g, '<br>') +
                    '</div>' +
                    '<button onclick="navigator.clipboard.writeText(\'' + diagText + '\').then(() => { this.textContent = \'✓ Copied!\'; setTimeout(() => this.textContent = \'Copy to clipboard\', 2000); })" style="margin-top:12px;padding:10px 20px;background:#333;color:#fff;border:none;border-radius:4px;cursor:pointer;font-size:13px;">Copy to clipboard</button>' +
                    '<p style="font-size:11px;color:#666;margin-top:12px;">Our engineer can remotely debug or setup your unit using this info. Share via WhatsApp, Telegram, or email.</p>';
            } catch (err) {
                status.className = 'status success';
                status.innerHTML = '<b>Request sent.</b><br>The artwork is joining <b>' + ssid + '</b>.<br>You can close this page.';
            }
        };
    </script>
</body>
</html>"""


class WiFiPortalHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass  # Suppress HTTP logs

    def get_system_info(self):
        """Gather diagnostic info to show the user"""
        info = {}
        try:
            # Hostname / unit ID
            info['unit'] = subprocess.run(['hostname'], capture_output=True, text=True).stdout.strip()
            
            # Uptime
            uptime = subprocess.run(['uptime', '-p'], capture_output=True, text=True).stdout.strip()
            info['uptime'] = uptime.replace('up ', '')
            
            # Ethernet IP (if connected)
            result = subprocess.run(['ip', '-4', 'addr', 'show', 'eth0'], capture_output=True, text=True)
            if 'inet ' in result.stdout:
                info['eth0_ip'] = result.stdout.split('inet ')[1].split()[0]
            
            # RustDesk ID (if installed)
            result = subprocess.run(['sudo', '-u', 'sjc', 'rustdesk', '--get-id'], 
                                   capture_output=True, text=True, timeout=3)
            if result.returncode == 0 and result.stdout.strip():
                info['rustdesk_id'] = result.stdout.strip()
            
            # WiFi signal strength from active connection
            result = subprocess.run(['nmcli', '-t', '-f', 'ACTIVE,SIGNAL', 'con', 'show', '--active'],
                                   capture_output=True, text=True)
            for line in result.stdout.strip().split('\n'):
                if ':yes' in line or 'yes:' in line:
                    parts = line.split(':')
                    if len(parts) >= 2:
                        info['wifi_signal'] = parts[-1] + '%'
                        break
            else:
                # Fallback: read from /proc/net/wireless
                try:
                    with open('/proc/net/wireless') as f:
                        for line in f:
                            if 'wlan0' in line:
                                parts = line.split()
                                if len(parts) >= 3:
                                    # Signal is in dBm, convert to percentage
                                    dbm = float(parts[2])
                                    pct = max(0, min(100, int((dbm + 100) * 2)))
                                    info['wifi_signal'] = f"{pct}% ({int(dbm)} dBm)"
                                    break
                except:
                    info['wifi_signal'] = 'unknown'
        except Exception as e:
            log.warning(f"Failed to gather system info: {e}")
        return info

    def do_GET(self):
        if self.path == '/' or self.path == '/index.html':
            self.send_response(200)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            page = HTML_PAGE.replace('UNIT_ID', HOTSPOT_SSID.replace('-SETUP', ''))
            self.wfile.write(page.encode())
        elif self.path == '/header.jpg':
            img_path = Path(__file__).parent / 'header.jpg'
            if img_path.exists():
                self.send_response(200)
                self.send_header('Content-type', 'image/jpeg')
                self.send_header('Content-Length', str(img_path.stat().st_size))
                self.end_headers()
                self.wfile.write(img_path.read_bytes())
            else:
                self.send_response(404)
                self.end_headers()
        elif self.path == '/scan':
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            networks = self.scan_networks()
            self.wfile.write(json.dumps({"networks": networks}).encode())
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        if self.path == '/connect':
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length).decode()
            params = parse_qs(post_data)
            ssid = params.get('ssid', [''])[0]
            password = params.get('password', [''])[0]
            
            log.info(f"Connection request: {ssid}")
            
            # Gather diagnostic info before we potentially lose connectivity
            sysinfo = self.get_system_info()
            
            # Send response IMMEDIATELY before we tear down the hotspot
            import hashlib
            ref = hashlib.md5(f"{ssid}{time.time()}".encode()).hexdigest()[:8].upper()
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({
                "success": True,
                "ref": ref,
                "unit": sysinfo.get('unit', 'unknown'),
                "uptime": sysinfo.get('uptime', 'unknown'),
                "eth0_ip": sysinfo.get('eth0_ip', 'not connected'),
                "rustdesk_id": sysinfo.get('rustdesk_id', 'not installed'),
                "wifi_signal": sysinfo.get('wifi_signal', 'unknown')
            }).encode())
            self.wfile.flush()
            
            # Now connect in a background thread (hotspot will drop, that's OK)
            threading.Thread(target=self.connect_wifi, args=(ssid, password), daemon=True).start()
        else:
            self.send_response(404)
            self.end_headers()

    def scan_networks(self):
        try:
            result = subprocess.run(
                ['nmcli', '-t', '-f', 'SSID,SIGNAL', 'dev', 'wifi', 'list'],
                capture_output=True, text=True, timeout=10
            )
            networks = []
            for line in result.stdout.strip().split('\n'):
                if ':' in line:
                    parts = line.split(':')
                    if len(parts) >= 2 and parts[0]:
                        networks.append({
                            'ssid': parts[0],
                            'signal': parts[1] if parts[1].isdigit() else '50'
                        })
            return sorted(networks, key=lambda x: int(x['signal']), reverse=True)[:10]
        except Exception as e:
            log.error(f"Scan failed: {e}")
            return []

    def connect_wifi(self, ssid, password):
        try:
            log.info(f"Attempting connection to {ssid}")
            
            # CRITICAL: bring down the hotspot FIRST — same radio can't do both
            subprocess.run(['nmcli', 'connection', 'down', 'Hotspot'],
                          capture_output=True, timeout=5)
            log.info("Hotspot down, connecting to target network...")
            
            # Delete old connection if exists
            subprocess.run(['nmcli', 'connection', 'delete', ssid], 
                          capture_output=True, timeout=5)
            # Add new connection
            result = subprocess.run([
                'nmcli', 'connection', 'add',
                'type', 'wifi',
                'ifname', 'wlan0',
                'con-name', ssid,
                'ssid', ssid,
                'wifi-sec.key-mgmt', 'wpa-psk',
                'wifi-sec.psk', password
            ], capture_output=True, text=True, timeout=10)
            
            if result.returncode != 0:
                log.error(f"Failed to create connection: {result.stderr}")
                return {"success": False, "error": "Failed to create connection"}
            
            # Try to connect
            result = subprocess.run(['nmcli', 'connection', 'up', ssid],
                                  capture_output=True, text=True, timeout=20)
            
            if result.returncode == 0:
                log.info(f"Connected to {ssid}")
                # Mark as configured
                CONFIG_FILE.touch()
                return {"success": True}
            else:
                log.error(f"Connection failed: {result.stderr}")
                return {"success": False, "error": "Connection failed - check password"}
        except Exception as e:
            log.error(f"Connect failed: {e}")
            return {"success": False, "error": str(e)}

    def stop_hotspot(self):
        subprocess.run(['nmcli', 'connection', 'down', 'Hotspot'],
                      capture_output=True)
        subprocess.run(['systemctl', 'stop', 'wifi-portal'],
                      capture_output=True)


def check_wifi_configured():
    """Check if we have a working WiFi connection"""
    try:
        result = subprocess.run(['nmcli', '-t', '-f', 'GENERAL.STATE', 'dev', 'show', 'wlan0'],
                              capture_output=True, text=True, timeout=5)
        return 'connected' in result.stdout.lower()
    except:
        return False


def start_hotspot():
    """Create WiFi hotspot with DNS hijacking for captive portal"""
    global HOTSPOT_SSID
    hostname = subprocess.run(['hostname'], capture_output=True, text=True).stdout.strip()
    HOTSPOT_SSID = f"{hostname.upper()}-SETUP"
    
    log.info(f"Starting hotspot: {HOTSPOT_SSID}")
    
    # Create hotspot
    subprocess.run([
        'nmcli', 'device', 'wifi', 'hotspot',
        'ifname', 'wlan0',
        'con-name', 'Hotspot',
        'ssid', f"DARKLABYRINTH-{HOTSPOT_SSID.replace('-SETUP', '')}",
        'password', 'dreammachine'
    ], timeout=10)
    
    # DNS hijack via NetworkManager's dnsmasq config
    try:
        dnsmasq_conf = Path('/etc/NetworkManager/dnsmasq-shared.d/captive-portal.conf')
        subprocess.run(['sudo', 'mkdir', '-p', str(dnsmasq_conf.parent)], check=True)
        subprocess.run(['sudo', 'sh', '-c', f'echo "address=/#/{HOTSPOT_IP}" > {dnsmasq_conf}'], check=True)
        # Reload NetworkManager's dnsmasq to pick up the config
        subprocess.run(['sudo', 'killall', '-HUP', 'dnsmasq'], capture_output=True)
        log.info("DNS hijack configured")
    except Exception as e:
        log.warning(f"DNS hijack failed (portal will still work manually): {e}")
    
    log.info(f"Hotspot active. Connect to {HOTSPOT_SSID}")


def main():
    # If already configured, exit
    if CONFIG_FILE.exists() and check_wifi_configured():
        log.info("WiFi already configured, exiting")
        return
    
    # Start hotspot
    start_hotspot()
    
    # Wait for hotspot IP to be assigned (NetworkManager is async)
    log.info("Waiting for hotspot IP assignment...")
    for _ in range(30):
        result = subprocess.run(['ip', 'addr', 'show', 'wlan0'],
                              capture_output=True, text=True)
        if HOTSPOT_IP in result.stdout:
            log.info(f"Hotspot IP {HOTSPOT_IP} is up")
            break
        time.sleep(1)
    
    # Start web server on all interfaces (more reliable than specific IP)
    server = HTTPServer(('0.0.0.0', 80), WiFiPortalHandler)
    log.info(f"Portal running at http://{HOTSPOT_IP}")
    server.serve_forever()


if __name__ == '__main__':
    main()
