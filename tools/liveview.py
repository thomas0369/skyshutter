#!/usr/bin/env python3
"""Pull live-view frames over PTP/IP from the camera's own WiFi network.

Pure stdlib client (skyshutter package): connects to the camera's PTP/IP
port 15740 in the network the camera's access point provides (default host
is the camera's usual address there), starts live view and saves JPEGs.

    python tools/liveview.py --frames 3 --out /tmp/lv

Prereqs: the camera AP is up and the machine joined it (remote-start --join,
or a rig like the Raspberry does both). Prints device info, starts live
view, saves JPEGs.
"""

from __future__ import annotations

import argparse
import os
import sys
import uuid

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

from skyshutter.nikon import NikonCamera

# The GUID SnapBridge uses; harmless as an initiator id for PTP/IP.
APP_GUID = uuid.UUID("00112233-4455-6677-8899-AABBCCDDEEFF")


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--host", default="192.168.0.10", help="camera IP in its own network")
    p.add_argument("--port", type=int, default=15740)
    p.add_argument("--frames", type=int, default=3, help="how many live-view frames to grab")
    p.add_argument("--out", default="/tmp/lv", help="output path prefix for JPEGs")
    p.add_argument("--name", default="skyshutter", help="PTP/IP friendly name")
    args = p.parse_args()

    print(f"connecting PTP/IP to {args.host}:{args.port} ...", flush=True)
    with NikonCamera.open(args.host, port=args.port, guid=APP_GUID, friendly_name=args.name) as cam:
        info = cam.refresh_device_info()
        model = getattr(info, "model", None) or getattr(info, "device_version", "?")
        print(f"connected. device: {model!r}", flush=True)

        print("starting live view ...", flush=True)
        cam.start_live_view()
        got = 0
        for _ in range(args.frames * 4):  # allow retries; the first frames can be empty
            jpeg = cam.get_live_view_frame()
            if jpeg:
                path = f"{args.out}_{got:02d}.jpg"
                with open(path, "wb") as fh:
                    fh.write(jpeg)
                print(f"  frame {got}: {len(jpeg)} bytes -> {path}", flush=True)
                got += 1
                if got >= args.frames:
                    break
        cam.end_live_view()
        if got == 0:
            print("no frames -- live view returned empty", flush=True)
            return 3
        print(f"done, {got} frame(s) saved.", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
