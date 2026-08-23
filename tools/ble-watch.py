#!/usr/bin/env python3
"""Continuous camera scanner -- what the maker app's menu does, for us.

The Nikon app shows the camera the moment it appears because it scans
CONTINUOUSLY while its device menu is open. Our scripts did one-shot scans
and hoped. This tool closes that gap on the Raspberry (BlueZ makes scanning
cheap there): it scans forever, filters for the camera's LSS service UUID and
Nikon manufacturer data, decodes the LSS ad-info byte (quickWakeUp /
autoTransfer / btcCoopWait -- the camera's readiness, readable WITHOUT
connecting) and publishes every sighting to a small status file:

    /tmp/camera_seen.json
        {"ts": <epoch>, "addr": ..., "rssi": ..., "name": ..., "flags": {...}}

Advertising start/stop phases are logged to stdout (journald under systemd),
which finally QUANTIFIES the camera's advertising pauses (playbook trap 6).

Modes:
    ble-watch.py            run the scanner forever
    ble-watch.py status     print the last sighting; exit 0 = fresh (<10 s),
                            2 = stale, 3 = never seen
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import time

try:
    from bleak import BleakScanner
except ImportError:  # pragma: no cover - bench tool
    sys.exit("bleak is missing: pip install bleak")

VENDOR = "-3dd4-4255-8d62-6dc7b9bd5561"
SERVICE = f"0000de00{VENDOR}"
NIKON_COMPANY = 0x0399

STATUS_FILE = os.environ.get("SKYSHUTTER_CAM_STATUS", "/tmp/camera_seen.json")
STALE_AFTER = 10.0  # seconds until a sighting no longer counts as fresh
LOST_AFTER = 20.0  # seconds of silence before we call the phase "lost"


def decode_flags(manufacturer: bytes | None) -> dict:
    """LSS ad-info byte is payload[4] (without company id); measured 23.08."""
    if not manufacturer or len(manufacturer) < 5:
        return {}
    b = manufacturer[4]
    return {
        "quickWakeUp": bool(b & 0x08),
        "autoTransfer": bool(b & 0x02),
        "btcCoopWait": bool(b & 0x10),
        "raw": f"0x{b:02x}",
    }


def write_status(payload: dict) -> None:
    """Atomic write so readers never see a half-written file."""
    d = os.path.dirname(STATUS_FILE) or "/tmp"
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".camseen_")
    try:
        with os.fdopen(fd, "w") as fh:
            json.dump(payload, fh)
        os.replace(tmp, STATUS_FILE)
    except OSError:
        try:
            os.unlink(tmp)
        except OSError:
            pass


def load_status() -> dict | None:
    try:
        with open(STATUS_FILE) as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


def run_status() -> int:
    data = load_status()
    if data is None:
        print("camera: nie gesehen")
        return 3
    age = time.time() - data.get("ts", 0)
    flags = data.get("flags", {})
    f = " ".join(f"{k}={v}" for k, v in flags.items() if k != "raw") or "keine"
    print(
        f"camera: gesehen vor {age:.1f}s  rssi={data.get('rssi')}  "
        f"addr={data.get('addr')}  flags: {f}"
    )
    return 0 if age < STALE_AFTER else 2


async def run_scanner() -> None:
    last_seen = 0.0
    phase = "lost"
    pause_start = time.monotonic()

    def cb(device, adv) -> None:
        nonlocal last_seen, phase, pause_start
        uuids = [u.lower() for u in (adv.service_uuids or [])]
        md = adv.manufacturer_data or {}
        nikon = md.get(NIKON_COMPANY)
        if SERVICE not in uuids and nikon is None:
            return
        now = time.time()
        payload = {
            "ts": now,
            "addr": device.address,
            "name": device.name,
            "rssi": adv.rssi if adv.rssi is not None else getattr(device, "rssi", None),
            "flags": decode_flags(bytes(nikon) if nikon else None),
        }
        write_status(payload)
        last_seen = now
        if phase == "lost":
            phase = "seen"
            gap = time.monotonic() - pause_start
            print(
                f"{time.strftime('%H:%M:%S')}  AD-Phase START "
                f"(Pause war {gap:.0f}s)  rssi={payload['rssi']} "
                f"flags={payload['flags']}",
                flush=True,
            )

    async with BleakScanner(detection_callback=cb):
        print(
            f"{time.strftime('%H:%M:%S')}  scanner aktiv, filter={SERVICE} "
            f"+ manufacturer 0x{NIKON_COMPANY:04x}",
            flush=True,
        )
        while True:
            await asyncio.sleep(5)
            if phase == "seen" and time.time() - last_seen > LOST_AFTER:
                phase = "lost"
                pause_start = time.monotonic()
                print(
                    f"{time.strftime('%H:%M:%S')}  AD-Phase ENDE "
                    f"(sichtbar {LOST_AFTER:.0f}s+ Stille)",
                    flush=True,
                )


if __name__ == "__main__":
    import asyncio

    p = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    p.add_argument(
        "mode",
        nargs="?",
        choices=["watch", "status"],
        default="watch",
        help="watch = scan forever (default), status = print last sighting",
    )
    args = p.parse_args()
    sys.exit(run_status() if args.mode == "status" else asyncio.run(run_scanner()))
