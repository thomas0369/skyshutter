#!/usr/bin/env python3
"""One approved test: does a remote capture (9207) kill the live view stream?

Runs its own PTP session (the stream service must be stopped -- single
client). Measures frame timing before/after the shot and object count.
"""

import sys
import time

sys.path.insert(0, "/home/thomas/projekte_hardware/skyshutter/src")
from skyshutter import config
from skyshutter.nikon import NikonCamera
from skyshutter.ptp import PtpError

SET_CONTROL_MODE = 0x90C2
INITIATE_CAPTURE = 0x9207
GET_OBJECT_HANDLES = 0x1007


def frames(cam, seconds, label):
    """Poll live view frames for a while, return (count, gaps_ms, errors)."""
    t0 = time.monotonic()
    stamps = []
    errors = 0
    while time.monotonic() - t0 < seconds:
        try:
            f = cam.get_live_view_frame()
        except PtpError:
            errors += 1
            time.sleep(0.3)
            continue
        if f:
            stamps.append(time.monotonic() - t0)
        else:
            errors += 1
        time.sleep(0.01)
    n = len(stamps)
    gaps = [round((b - a) * 1000) for a, b in zip(stamps, stamps[1:])]
    if gaps:
        med = sorted(gaps)[len(gaps) // 2]
        print(
            f"{label}: {n} Frames in {seconds:.0f}s = {n / seconds:.1f} fps, "
            f"Abstand median {med} ms, Fehler/Pausen: {errors}"
        )
    else:
        print(f"{label}: KEINE Frames, Fehler: {errors}")
    return n, gaps, errors


def object_count(cam):
    r = cam.connection.transaction(
        GET_OBJECT_HANDLES, (0xFFFFFFFF, 0, 0, 0xFFFFFFFF), raise_on_error=False
    )
    if not r.ok:
        return None
    data = r.data
    return int.from_bytes(data[:4], "little")


with NikonCamera.open(
    "192.168.0.10",
    guid=config.client_guid(None),
    friendly_name=config.client_name(None),
    timeout=15,
) as cam:
    print("Session steht.")
    r = cam.connection.transaction(SET_CONTROL_MODE, (1,), raise_on_error=False)
    print(f"ControlMode 1: ok={r.ok} code=0x{r.response_code:04x}")
    time.sleep(3)

    try:
        cam.start_live_view(attempts=20, pause=1.0)
        print("StartLiveView OK")
    except PtpError as e:
        print(f"StartLiveView: {e} -- versuche weiter (Frames koennen trotzdem kommen)")

    time.sleep(2)

    frames(cam, 5, "VOR  ")

    n_before = object_count(cam)
    print(f"Objekte auf der Karte vorher: {n_before}")

    print("--> InitiateCaptureRecInMedia (0x9207) params (0, 0) ...")
    t_shot = time.monotonic()
    r = cam.connection.transaction(INITIATE_CAPTURE, (0, 0), raise_on_error=False)
    print(f"    Antwort: ok={r.ok} code=0x{r.response_code:04x}")

    # Direkt danach: jede Sekunde probieren, wann Frames wiederkommen
    t0 = time.monotonic()
    first_back = None
    while time.monotonic() - t0 < 40:
        try:
            f = cam.get_live_view_frame()
        except PtpError:
            f = None
        if f:
            first_back = time.monotonic() - t_shot
            break
        time.sleep(0.5)
    if first_back is not None:
        print(f"    Erster Frame wieder da: {first_back:.1f}s nach dem Ausloeser")
    else:
        print("    KEIN Frame innerhalb 40s nach dem Ausloeser!")

    time.sleep(2)
    frames(cam, 8, "NACH ")

    n_after = object_count(cam)
    print(f"Objekte auf der Karte nachher: {n_after} (vorher: {n_before})")
    if n_before is not None and n_after is not None:
        print(
            f"    --> {'AUFNAHME GEMACHT: +' + str(n_after - n_before) + ' Objekt(e)' if n_after > n_before else 'KEIN neues Objekt -- Ausloeser nicht durchgedrungen'}"
        )
    print("Test fertig.")
