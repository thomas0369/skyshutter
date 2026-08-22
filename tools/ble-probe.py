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
import os
import sys

try:
    from bleak import BleakClient, BleakScanner
except ImportError:  # pragma: no cover - bench tool
    sys.exit("bleak is missing: pip install bleak")

DEFAULT_NAME = "P1100_SSSSSSSS"
AUTH_LENGTH = 17
VENDOR_SERVICE = "0000de00-3dd4-4255-8d62-6dc7b9bd5561"


def hexdump(data: bytes) -> str:
    text = "".join(chr(c) if 32 <= c < 127 else "." for c in data)
    return f"{len(data):3}B  {data.hex()}  |{text}|"


async def find(args):
    """Scan until the camera shows up.

    It only advertises while *Connect to smart device* is open on its own
    screen — leave that menu and it goes silent within seconds. So a scan that
    finds nothing usually means nobody is standing at the camera, not that
    anything is broken. Its address is a resolvable private one and rotates,
    so match on the name.
    """
    def matches(device, adv) -> bool:
        # Never match on the name. The advertisement carries a 128-bit service
        # UUID, which eats 16 of the 31 payload bytes, so the camera ships a
        # shortened local name -- 'P110' -- and a name lookup finds nothing.
        # The service UUID is the reliable marker, and unlike the address
        # (resolvable private, rotates every scan) it does not change.
        return any(u.lower() == VENDOR_SERVICE for u in adv.service_uuids)

    for attempt in range(1, args.retries + 1):
        device = await BleakScanner.find_device_by_filter(matches, timeout=args.timeout)
        if device is not None:
            return device
        print(f"  scan {attempt}/{args.retries}: silent", file=sys.stderr, flush=True)
    sys.exit("camera not advertising - open the smart-device menu on the camera")


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
    device = await find(args)
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
    device = await find(args)
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
    device = await find(args)
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


async def connect(args):
    """Scan and connect, retrying both.

    Finding the camera and connecting to it are separate failures with
    separate causes: it stops advertising when its menu closes, and it refuses
    connections for reasons still unclear. Retrying the pair of them is the
    only thing that has worked reliably.
    """
    for attempt in range(1, args.retries + 1):
        device = await find(args)
        client = BleakClient(device, timeout=args.timeout)
        try:
            await client.connect()
        except Exception as exc:
            print(
                f"  connect {attempt}/{args.retries} to {device.address}: "
                f"{type(exc).__name__}",
                file=sys.stderr,
                flush=True,
            )
            await asyncio.sleep(2)
            continue

        # A connection can come up hollow: it reports success, negotiates the
        # minimum MTU of 23 and exposes no services at all. Treat that as a
        # failure -- it is indistinguishable from a working link until the
        # first read fails with "characteristic not found".
        if not any(s.uuid.lower() == VENDOR_SERVICE for s in client.services):
            print(
                f"  connect {attempt}/{args.retries}: hollow "
                f"(mtu={client.mtu_size}, no vendor service)",
                file=sys.stderr,
                flush=True,
            )
            await client.disconnect()
            await asyncio.sleep(2)
            continue
        return client
    sys.exit("found the camera but could not get a usable connection")


async def cmd_session(args) -> None:
    """Tree, values and live traffic in one connection.

    Reconnecting costs a scan each time and the camera is not always awake, so
    when it is reachable, take everything at once.
    """
    client = await connect(args)
    async with client:
        print(f"connected  mtu={client.mtu_size}\n")

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


async def cmd_pair(args) -> None:
    """Bond with the camera, the way the vendor app does.

    The camera asks for a button press on its own body while this runs. Note
    that it may only remember one bonded device, so pairing here can cost the
    phone its pairing.
    """
    device = await find(args)
    async with BleakClient(device, timeout=args.timeout) as client:
        print("connected; press OK on the camera when it asks", flush=True)
        try:
            paired = await client.pair()
        except Exception as exc:
            print(f"pairing failed: {type(exc).__name__}: {str(exc)[:120]}")
            return
        print("paired:", paired)
        if paired and args.seconds > 0:
            for service in client.services:
                for char in service.characteristics:
                    if not {"notify", "indicate"} & set(char.properties):
                        continue

                    def handler(sender, data, uuid=char.uuid):
                        print(f"  EVENT {uuid[4:8]}  {hexdump(bytes(data))}", flush=True)

                    try:
                        await client.start_notify(char, handler)
                    except Exception as exc:
                        print(f"  cannot subscribe {char.uuid[4:8]}: {str(exc)[:70]}")
            print(f"listening {args.seconds}s", flush=True)
            await asyncio.sleep(args.seconds)


AUTH_UUID = "00002000-3dd4-4255-8d62-6dc7b9bd5561"
NAME_UUID = "00002002-3dd4-4255-8d62-6dc7b9bd5561"


def auth_message(stage: int, stamp: bytes, device_id: bytes, nonce: bytes) -> bytes:
    """One 17-byte authentication message.

    Stage byte, 8-byte timestamp, 4-byte device id, 4-byte nonce. Published
    reverse engineering says the device id's least significant byte has to be
    0x01; since the fields are little-endian, that is the first byte.
    """
    for label, value, size in (("stamp", stamp, 8), ("id", device_id, 4), ("nonce", nonce, 4)):
        if len(value) != size:
            raise ValueError(f"{label} must be {size} bytes, got {len(value)}")
    return bytes([stage]) + stamp + device_id + nonce


async def cmd_handshake(args) -> None:
    """Run the first two stages of authentication and report what comes back.

    Stages 3 and 4 need a Blowfish step whose input is not yet worked out, so
    this stops after stage 2 on purpose. Stage 2 alone answers the question
    that matters right now: does the camera engage with an unknown client at
    all, or does it ignore it?
    """
    stamp = os.urandom(8)
    device_id = b"\x01" + os.urandom(3)
    nonce = os.urandom(4)
    stage1 = auth_message(0x01, stamp, device_id, nonce)

    client = await connect(args)
    async with client:
        print(f"connected  mtu={client.mtu_size}")
        before = bytes(await client.read_gatt_char(AUTH_UUID))
        print(f"  0x2000 before  {hexdump(before)}")

        print(f"  stage 1 write  {hexdump(stage1)}")
        try:
            await client.write_gatt_char(AUTH_UUID, stage1, response=True)
        except Exception as exc:
            print(f"  write refused: {type(exc).__name__}: {str(exc).splitlines()[0][:90]}")
            return

        await asyncio.sleep(1.0)
        reply = bytes(await client.read_gatt_char(AUTH_UUID))
        print(f"  stage 2 read   {hexdump(reply)}")

        if len(reply) == AUTH_LENGTH and reply[0] == 0x02:
            print("  -> camera answered with stage 2")
            print(f"     its timestamp  {reply[1:9].hex()}")
            print(f"     challenge id   {reply[9:13].hex()}")
            print(f"     challenge nonce{reply[13:17].hex()}")
            print(f"     our id was     {device_id.hex()}   nonce {nonce.hex()}")
        elif reply == before:
            print("  -> unchanged; the write had no visible effect")
        else:
            print(f"  -> unexpected reply, stage byte 0x{reply[0]:02x}" if reply else "  -> empty")


async def cmd_pairing(args) -> None:
    """Run the whole four-stage handshake and register as a client."""
    import nikon_pairing as np

    stage1 = np.stage_one()
    client = await connect(args)
    async with client:
        print(f"connected  mtu={client.mtu_size}")
        print(f"  before   {hexdump(bytes(await client.read_gatt_char(AUTH_UUID)))}")

        print(f"  stage 1  {hexdump(stage1.encode())}")
        await client.write_gatt_char(AUTH_UUID, stage1.encode(), response=True)
        await asyncio.sleep(1.0)

        stage2 = np.Message.decode(bytes(await client.read_gatt_char(AUTH_UUID)))
        print(f"  stage 2  {hexdump(stage2.encode())}")
        if stage2.stage != 0x02:
            print(f"  camera did not answer with stage 2 (got 0x{stage2.stage:02x})")
            return

        stage3 = np.stage_three(stage1, stage2)
        print(f"  salt     #{np.find_salt(stage1, stage2)}")
        print(f"  stage 3  {hexdump(stage3.encode())}")
        await client.write_gatt_char(AUTH_UUID, stage3.encode(), response=True)
        await asyncio.sleep(1.0)

        stage4 = np.Message.decode(bytes(await client.read_gatt_char(AUTH_UUID)))
        print(f"  stage 4  {hexdump(stage4.encode())}")
        if stage4.stage != 0x04:
            print(f"  handshake rejected at stage 4 (got 0x{stage4.stage:02x})")
            return
        print(f"  -> authenticated; camera serial {stage4.serial!r}")
        print(f"  -> remember  device={stage1.device.hex()} nonce={stage1.nonce.hex()}")

        if args.register:
            payload = np.client_name(args.register)
            print(f"  name     {hexdump(payload)}")
            await client.write_gatt_char(NAME_UUID, payload, response=True)
            print(f"  -> registered as {args.register!r}")

        if args.seconds > 0:
            for service in client.services:
                for char in service.characteristics:
                    if not {"notify", "indicate"} & set(char.properties):
                        continue

                    def handler(sender, data, uuid=char.uuid):
                        print(f"  EVENT {uuid[4:8]}  {hexdump(bytes(data))}", flush=True)

                    try:
                        await client.start_notify(char, handler)
                    except Exception:
                        pass
            print(f"  listening {args.seconds}s", flush=True)
            await asyncio.sleep(args.seconds)


async def cmd_unpair(args) -> None:
    """Drop the bond again.

    A half-finished pairing is worse than none: Windows stores the bond, the
    camera does not, and every later connection attempt then dies in an
    encryption handshake that cannot succeed. Symptom is a connect timeout on
    a device that scanning finds without trouble.
    """
    device = await find(args)
    client = BleakClient(device, timeout=args.timeout)
    try:
        result = await client.unpair()
    except Exception as exc:
        print(f"unpair failed: {type(exc).__name__}: {str(exc)[:120]}")
        return
    print("unpair:", result)


async def cmd_write(args) -> None:
    if not args.i_know:
        sys.exit("refusing to write without --i-know")
    payload = bytes.fromhex(args.hex)
    device = await find(args)
    async with BleakClient(device, timeout=args.timeout) as client:
        print(f"write {args.uuid} <- {payload.hex()}")
        await client.write_gatt_char(args.uuid, payload, response=not args.no_response)
        print("accepted")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--name", default=DEFAULT_NAME, help="advertised device name")
    parser.add_argument("--timeout", type=float, default=25.0)
    parser.add_argument("--retries", type=int, default=4, help="scan attempts before giving up")
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

    pair = sub.add_parser("pair", help="bond with the camera (needs a button press on it)")
    pair.add_argument("--seconds", type=float, default=30.0, help="listen after pairing")
    pair.set_defaults(run=cmd_pair)

    sub.add_parser("handshake", help="run stages 1-2 of authentication").set_defaults(
        run=cmd_handshake
    )

    pairing = sub.add_parser("pairing", help="run the full four-stage handshake")
    pairing.add_argument("--register", metavar="NAME", help="write this client name to 0x2002")
    pairing.add_argument("--seconds", type=float, default=0.0, help="listen afterwards")
    pairing.set_defaults(run=cmd_pairing)
    sub.add_parser("unpair", help="drop the bond").set_defaults(run=cmd_unpair)

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
