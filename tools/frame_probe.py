#!/usr/bin/env python3
"""Secure one remote-mode frame and report its dimensions."""

import struct
import sys
import time

sys.path.insert(0, "/home/thomas/projekte_hardware/skyshutter/src")
from skyshutter import config
from skyshutter.nikon import NikonCamera

SET_CONTROL_MODE = 0x90C2

with NikonCamera.open(
    "192.168.0.10",
    guid=config.client_guid(None),
    friendly_name=config.client_name(None),
    timeout=15,
) as cam:
    cam.connection.transaction(SET_CONTROL_MODE, (1,), raise_on_error=False)
    time.sleep(2)
    f = cam.get_live_view_frame()
    if f:
        d = f
        i = 2
        while i < len(d):
            if d[i] != 0xFF:
                break
            m = d[i + 1]
            if m in (0xC0, 0xC2):
                h, w = struct.unpack(">HH", d[i + 5 : i + 9])
                print(f"Frame: {w}x{h}, {len(d)} bytes")
                break
            ln = struct.unpack(">H", d[i + 2 : i + 4])[0]
            i += 2 + ln
        with open("/tmp/remote_frame.jpg", "wb") as fh:
            fh.write(d)
        print("Frame gesichert: /tmp/remote_frame.jpg")
    else:
        print("kein Frame")
