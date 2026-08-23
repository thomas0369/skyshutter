#!/usr/bin/env python3
"""Connect out to the camera's classic Bluetooth serial service, like the app.

The btsnoop of a working SnapBridge remote-photography session shows the app
does NOT wait for the camera on RFCOMM -- it connects *out* to the camera's own
SPP service, UUID 5e8945b0-9525-11e3-a5e2-0800200c9a66. Our earlier
rfcomm-listen.py had the direction backwards. Without this classic connection
the camera stays INVALID_WAKE and ignores the 0x2005 WiFi-establishment write,
which is why every BLE-only attempt to raise the access point failed.

This finds the paired camera, opens that RFCOMM service and holds it, dumping
anything that arrives. A classic connection to a bonded device needs no
advertising window, so the camera only has to be on and in range.

    python tools/rfcomm-connect.py --hold 60

Pair first (classic-pair.py pair). Runs under the Windows Python.
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
