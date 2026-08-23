#!/usr/bin/env python3
"""Connect out to a classic Bluetooth serial (SPP) service on a bonded device.

!!! MISATTRIBUTED TARGET -- kept only as a general SPP-client tool. !!!
The btsnoop RFCOMM connect to UUID 5e8945b0-9525-11e3-a5e2-0800200c9a66 was
first read as SnapBridge->camera, but the deep-dive (23.08.2026) proved it goes
to a Samsung "Watch Ultra" (addr ...2d:4c, dev_class 28:07:04); 5e8945b0 is a
Samsung UUID, not Nikon. The camera (P1100, ...4f:fe, dev_class 08:06:20) opens
NO RFCOMM data channel at all -- its only classic step is a createBond (SSP).
So this tool is NOT part of the camera flow. See docs/REMOTE_SEQUENCE.md.
The wake gate was also a misread: 0x2001=0x03 is VALID_WAKE, not INVALID_WAKE.

Left in place because an outgoing SPP client may still be useful elsewhere.

    python tools/rfcomm-connect.py --hold 60

Runs under the Windows Python.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import time
from uuid import UUID

try:
    from winrt.windows.devices.bluetooth import BluetoothCacheMode, BluetoothDevice
    from winrt.windows.devices.bluetooth.rfcomm import RfcommServiceId
    from winrt.windows.devices.enumeration import DeviceInformation
    from winrt.windows.networking.sockets import SocketProtectionLevel, StreamSocket
    from winrt.windows.storage.streams import DataReader
except ImportError:  # pragma: no cover - bench tool
    sys.exit("needs the Windows Python with winrt-Windows.Devices.Bluetooth[.Rfcomm] etc.")

NIKON_SPP = "5e8945b0-9525-11e3-a5e2-0800200c9a66"


def log(message: str) -> None:
    print(f"{time.strftime('%H:%M:%S')}  {message}", flush=True)


def hexdump(data: bytes) -> str:
    text = "".join(chr(c) if 32 <= c < 127 else "." for c in data)
    return f"{len(data):3}B  {data.hex()}  |{text}|"


async def find_camera(name_hint: str):
    """Return the paired BluetoothDevice whose name matches, or None."""
    selector = BluetoothDevice.get_device_selector_from_pairing_state(True)
    found = await DeviceInformation.find_all_async_aqs_filter(selector)
    for i in range(found.size):
        info = found.get_at(i)
        try:
            dev = await BluetoothDevice.from_id_async(info.id)
        except Exception:
            continue
        if dev is None:
            continue
        nm = dev.name or info.name or ""
        if name_hint.lower() in nm.lower():
            return dev, nm
    return None, None


async def run(args) -> None:
    service_id = RfcommServiceId.from_uuid(UUID(args.uuid))

    dev, nm = await find_camera(args.name)
    if dev is None:
        sys.exit(
            f"No paired device matching {args.name!r}. Pair first (classic-pair.py pair) "
            "and make sure the camera is on and in range."
        )
    log(f"camera: {nm!r}  (address {dev.bluetooth_address:012x})")

    # Uncached forces a fresh SDP query so we see the service even if Windows
    # cached an older record from before remote photography was available.
    services = await dev.get_rfcomm_services_for_id_with_cache_mode_async(
        service_id, BluetoothCacheMode.UNCACHED
    )
    if services is None or services.services.size == 0:
        sys.exit(
            f"The camera does not expose SPP service {args.uuid}. It may only offer it "
            "in a certain state -- try again with remote photography prepared on the camera."
        )
    service = services.services.get_at(0)
    log(f"found SPP service, connecting on {service.connection_service_name}")

    socket = StreamSocket()
    level = (
        SocketProtectionLevel.BLUETOOTH_ENCRYPTION_WITH_AUTHENTICATION
        if args.encrypt
        else SocketProtectionLevel.PLAIN_SOCKET
    )
    try:
        await socket.connect_async(
            service.connection_host_name, service.connection_service_name, level
        )
    except Exception as exc:
        sys.exit(f"connect failed: {type(exc).__name__}: {str(exc).splitlines()[0][:110]}")
    log("RFCOMM connected -- the camera should now count us as a live client")

    reader = DataReader(socket.input_stream)
    reader.input_stream_options = 1  # partial: return whatever is there
    elapsed = 0.0
    try:
        while elapsed < args.hold:
            try:
                count = await asyncio.wait_for(reader.load_async(4096), timeout=2.0)
            except asyncio.TimeoutError:
                count = 0
            except Exception as exc:
                log(f"read ended: {type(exc).__name__}: {str(exc)[:70]}")
                break
            if count:
                log(f"RECV {hexdump(bytes(reader.read_buffer(count)))}")
            elapsed += 2.0
    except KeyboardInterrupt:
        pass
    finally:
        socket.close()
        log("closed")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--name", default="P1100", help="substring of the paired device name")
    parser.add_argument("--uuid", default=NIKON_SPP, help="RFCOMM service UUID to connect to")
    parser.add_argument("--hold", type=float, default=60.0, help="seconds to stay connected")
    parser.add_argument(
        "--encrypt", action="store_true", help="require an encrypted link (the app does)"
    )
    args = parser.parse_args()
    asyncio.run(run(args))


if __name__ == "__main__":
    main()
