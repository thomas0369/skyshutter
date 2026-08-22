#!/usr/bin/env python3
"""Talk to the camera over BLE, from the measuring side.

This is a bench instrument, not part of skyshutter. It lives outside the
package on purpose: it needs a BLE stack (bleak), and the package itself stays
standard-library only. It also has to run on the Windows Python, because WSL
has no Bluetooth adapter of its own.

    pip install bleak
    python tools/ble-probe.py scan
    python tools/ble-probe.py dump
    python tools/ble-probe.py read
    python tools/ble-probe.py watch --seconds 60

The read and watch subcommands only read. Writing to the camera is a separate
subcommand that refuses to run without --i-know, because a wrong byte on an
unknown characteristic is the one thing here that could change camera state.
"""

from __future__ import annotations

import argparse
import asyncio
import sys

try:
    from bleak import BleakClient, BleakScanner
except ImportError:  # pragma: no cover - bench tool
    sys.exit("bleak is missing: pip install bleak")

DEFAULT_NAME = "P1100_SSSSSSSS"
VENDOR_SERVICE = "0000de00-3dd4-4255-8d62-6dc7b9bd5561"


def hexdump(data: bytes) -> str:
    text = "".join(chr(c) if 32 <= c < 127 else "." for c in data)
    return f"{len(data):3}B  {data.hex()}  |{text}|"


async def find(name: str, timeout: float, retries: int = 4):
    """Scan until the camera shows up.

    It advertises in bursts and goes quiet in between, so a single scan that
    happens to land in a quiet stretch means nothing. Its address is a
    resolvable private one and rotates, so match on the name.
    """
    for attempt in range(1, retries + 1):
        device = await BleakScanner.find_device_by_name(name, timeout=timeout)
        if device is not None:
            return device
        print(f"  scan {attempt}/{retries}: silent", file=sys.stderr)
    sys.exit(f"{name} is not advertising - wake the camera and retry")


async def cmd_scan(args) -> None:
    seen: dict = {}

    def callback(device, adv):
        seen[device.address] = (adv.local_name or device.name, adv.rssi, list(adv.service_uuids))

    scanner = BleakScanner(callback)
    await scanner.start()
    await asyncio.sleep(args.seconds)
    await scanner.stop()

    print(f"{len(seen)} devices")
    for address, (name, rssi, uuids) in sorted(seen.items(), key=lambda kv: -kv[1][1]):
        mark = "  <-- camera" if any(u.lower() == VENDOR_SERVICE for u in uuids) else ""
        print(f"{address}  rssi={rssi:4}  name={name!r}{mark}")
        for uuid in uuids:
            print(f"    service {uuid}")


async def cmd_dump(args) -> None:
    device = await find(args.name, args.timeout)
    async with BleakClient(device, timeout=args.timeout) as client:
        print(f"connected {device.address}  mtu={client.mtu_size}")
        for service in client.services:
            print(f"\nSERVICE handle=0x{service.handle:04x} uuid={service.uuid}")
            for char in service.characteristics:
                props = ",".join(sorted(char.properties))
                # bleak reports the declaration handle; the value sits one above.
                print(
                    f"  CHAR decl=0x{char.handle:04x} value=0x{char.handle + 1:04x} "
                    f"uuid={char.uuid} props=[{props}]"
                )
                for desc in char.descriptors:
                    print(f"    DESC handle=0x{desc.handle:04x} uuid={desc.uuid}")


async def cmd_read(args) -> None:
    device = await find(args.name, args.timeout)
    async with BleakClient(device, timeout=args.timeout) as client:
        print(f"connected {device.address}  mtu={client.mtu_size}")
        for service in client.services:
            print(f"\n--- service {service.uuid[4:8]} ---")
            for char in service.characteristics:
                if "read" not in char.properties:
                    continue
                label = f"  {char.uuid[4:8]} @0x{char.handle:04x}"
                try:
                    value = bytes(await client.read_gatt_char(char))
                except Exception as exc:  # the error itself is the measurement
                    reason = str(exc).splitlines()[0][:90]
                    print(f"{label}  ERROR {type(exc).__name__}: {reason}")
                else:
                    print(f"{label}  {hexdump(value)}")


async def cmd_watch(args) -> None:
    device = await find(args.name, args.timeout)
    async with BleakClient(device, timeout=args.timeout) as client:
        print(f"connected {device.address}  mtu={client.mtu_size}")
        subscribed = []
        for service in client.services:
            for char in service.characteristics:
                if {"notify", "indicate"} & set(char.properties):
                    def handler(sender, data, uuid=char.uuid):
                        print(f"{uuid[4:8]}  {hexdump(bytes(data))}", flush=True)

                    try:
                        await client.start_notify(char, handler)
                        subscribed.append(char.uuid[4:8])
                    except Exception as exc:
                        print(f"  cannot subscribe {char.uuid[4:8]}: {exc}")
        print("subscribed:", ", ".join(subscribed) or "nothing")
        print(f"listening {args.seconds}s — operate the camera now")
        await asyncio.sleep(args.seconds)


async def cmd_session(args) -> None:
    """Tree, values and live traffic in one connection.

    Reconnecting costs a scan each time and the camera is not always awake, so
    when it is reachable, take everything at once.
    """
    device = await find(args.name, args.timeout)
    async with BleakClient(device, timeout=args.timeout) as client:
        print(f"connected {device.address}  mtu={client.mtu_size}\n")

        for service in client.services:
            print(f"SERVICE handle=0x{service.handle:04x} uuid={service.uuid}")
            for char in service.characteristics:
                props = ",".join(sorted(char.properties))
                line = (
                    f"  decl=0x{char.handle:04x} value=0x{char.handle + 1:04x} "
                    f"{char.uuid[4:8]} [{props}]"
                )
                if "read" in char.properties:
                    try:
                        value = bytes(await client.read_gatt_char(char))
                        line += f"\n      {hexdump(value)}"
                    except Exception as exc:
                        line += f"\n      ERROR {type(exc).__name__}: " \
                                f"{str(exc).splitlines()[0][:80]}"
                print(line)
                for desc in char.descriptors:
                    print(f"      DESC 0x{desc.handle:04x} {desc.uuid[4:8]}")
            print()

        if args.seconds <= 0:
            return
        subscribed = []
        for service in client.services:
            for char in service.characteristics:
                if not {"notify", "indicate"} & set(char.properties):
                    continue

                def handler(sender, data, uuid=char.uuid):
                    print(f"  EVENT {uuid[4:8]}  {hexdump(bytes(data))}", flush=True)

                try:
                    await client.start_notify(char, handler)
                    subscribed.append(char.uuid[4:8])
                except Exception as exc:
                    print(f"  cannot subscribe {char.uuid[4:8]}: {str(exc)[:70]}")
        print("subscribed:", ", ".join(subscribed) or "nothing")
        print(f"listening {args.seconds}s - operate the camera now", flush=True)
        await asyncio.sleep(args.seconds)


async def cmd_write(args) -> None:
    if not args.i_know:
        sys.exit("refusing to write without --i-know")
    payload = bytes.fromhex(args.hex)
    device = await find(args.name, args.timeout)
    async with BleakClient(device, timeout=args.timeout) as client:
        print(f"write {args.uuid} <- {payload.hex()}")
        await client.write_gatt_char(args.uuid, payload, response=not args.no_response)
        print("accepted")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--name", default=DEFAULT_NAME, help="advertised device name")
    parser.add_argument("--timeout", type=float, default=25.0)
    sub = parser.add_subparsers(dest="command", required=True)

    scan = sub.add_parser("scan", help="list advertising devices")
    scan.add_argument("--seconds", type=float, default=15.0)
    scan.set_defaults(run=cmd_scan)

    sub.add_parser("dump", help="print the GATT tree").set_defaults(run=cmd_dump)
    sub.add_parser("read", help="read every readable characteristic").set_defaults(run=cmd_read)

    watch = sub.add_parser("watch", help="subscribe to notify/indicate and print traffic")
    watch.add_argument("--seconds", type=float, default=60.0)
    watch.set_defaults(run=cmd_watch)

    session = sub.add_parser("session", help="dump, read and listen in one connection")
    session.add_argument("--seconds", type=float, default=45.0, help="0 skips listening")
    session.set_defaults(run=cmd_session)

    write = sub.add_parser("write", help="write one value (guarded)")
    write.add_argument("uuid")
    write.add_argument("hex", help="payload as hex, e.g. 0100")
    write.add_argument("--no-response", action="store_true")
    write.add_argument("--i-know", action="store_true", help="required acknowledgement")
    write.set_defaults(run=cmd_write)

    args = parser.parse_args()
    asyncio.run(args.run(args))


if __name__ == "__main__":
    main()
