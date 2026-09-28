#!/usr/bin/env python3
"""fls_trigger.py — send /fls/start or /fls/stop to the local LED controller.
Usage: fls_trigger.py [start|stop]   (default: start)
"""
import sys
from pythonosc.udp_client import SimpleUDPClient

action = sys.argv[1] if len(sys.argv) > 1 else "start"
if action not in ("start", "stop"):
    print(f"usage: {sys.argv[0]} [start|stop]")
    sys.exit(2)

client = SimpleUDPClient("127.0.0.1", 9000)
client.send_message(f"/fls/{action}", 1)
print(f"OSC-SENT /fls/{action}")
