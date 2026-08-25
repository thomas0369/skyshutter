#!/usr/bin/env python3
"""Measure remote-mode (ControlMode 1) live view frame timing on hardware.

Deployed to the Pi as /tmp/probe_mode.py by the measurement pipeline
(auto-measure.sh). Not part of the installed package.
"""

import sys
import time

sys.path.insert(0, "/home/thomas/projekte_hardware/skyshutter/src")
from skyshutter import config
from skyshutter.nikon import NikonCamera
from skyshutter.ptp import PtpError

SET_CONTROL_MODE = 0x90C2

with NikonCamera.open(
    "192.168.0.10",
    guid=config.client_guid(None),
    friendly_name=config.client_name(None),
    timeout=15,
) as cam:
    print("Verbindung steht.")

    r = cam.connection.transaction(SET_CONTROL_MODE, (1,), raise_on_error=False)
    print(f"ControlMode 1: ok={r.ok} code=0x{r.response_code:04x} (a003 = schon drin)")
    time.sleep(3)

    ready = cam.wait_until_ready(timeout=10)
    print(f"DeviceReady: {ready}")
    print(f"LiveViewStatus-Property: {cam.live_view_running()}")

    try:
        cam.start_live_view()
        print("StartLiveView OK")
    except PtpError as e:
        print(f"StartLiveView: {e} (weiter, evtl. laeuft schon)")

    time.sleep(2)

    times = []
    busy = 0
    for i in range(30):
        if len(times) >= 12:
            break
        t0 = time.monotonic()
        try:
            f = cam.get_live_view_frame()
        except PtpError as e:
            print(f"  retry {i}: {e}")
            busy += 1
            time.sleep(1.5)
            continue
        dt = time.monotonic() - t0
        if f:
            times.append(dt)
            print(f"{len(times):2d}: {dt * 1000:7.1f} ms  {len(f)} bytes")
        else:
            print(f"  {i}: None (busy)")
            busy += 1
            time.sleep(0.5)

    if times:
        med = sorted(times)[len(times) // 2]
        print(f"median {med * 1000:.0f} ms -> {1000 / med:.1f} fps  (Retries: {busy})")
    else:
        print(f"KEINE Frames. Retries/Busy: {busy}")
        print(f"LiveViewStatus jetzt: {cam.live_view_running()}")
