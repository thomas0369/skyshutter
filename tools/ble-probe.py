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
import struct
import sys
import time

try:
    from bleak import BleakClient, BleakScanner
except ImportError:  # pragma: no cover - bench tool
    sys.exit("bleak is missing: pip install bleak")

# Only a fallback: matching happens on the service UUID, because the advertised
# name is truncated anyway. The serial is left out on purpose -- it identifies
# the device and this repository is public.
DEFAULT_NAME = "P1100"
AUTH_LENGTH = 17
VENDOR_SERVICE = "0000de00-3dd4-4255-8d62-6dc7b9bd5561"


def log(message: str) -> None:
    """Print with a timestamp and flush, so a tail -f shows it at once."""
    print(f"{time.strftime('%H:%M:%S')}  {message}", flush=True)


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

    # A wall clock on top of the attempt count. Retries alone are a bad limit:
    # 30 of them at six seconds each is three minutes of someone standing at a
    # camera waiting for something that is not going to happen.
    deadline = time.monotonic() + args.give_up
    for attempt in range(1, args.retries + 1):
        if time.monotonic() > deadline:
            print(f"  aufgegeben nach {args.give_up:.0f}s", file=sys.stderr, flush=True)
            break
        device = await BleakScanner.find_device_by_filter(matches, timeout=args.timeout)
        if device is not None:
            return device
        left = max(0, deadline - time.monotonic())
        print(f"  scan {attempt}/{args.retries}: still, noch {left:.0f}s",
              file=sys.stderr, flush=True)
    sys.exit(
        "Kamera sendet nicht. Drei Ursachen, in dieser Reihenfolge pruefen:\n"
        "  1. Das Kameramenue 'Mit Smartgeraet verbinden' ist zu.\n"
        "  2. Die Kamera ist bereits verbunden -- steht ein Bluetooth-Symbol im\n"
        "     Display, advertisiert sie nicht mehr und kein Scan findet sie.\n"
        "     Abhilfe: Funk aus/an (bt_state.ps1), dann sendet sie wieder.\n"
        "  3. Der Windows-Stack hat sich verschluckt: mtu=23 statt 515 in den\n"
        "     Verbindungsversuchen oben. Auch dagegen hilft Funk aus/an."
    )


async def cmd_adwake(args) -> None:
    """Watch the camera's advertisement for its wake/readiness flags.

    The vendor scan parser (BleScanData) reads an "LSS ad info" byte from the
    manufacturer data and exposes three flags from it: quickWakeUp (bit 0x8),
    autoTransfer (bit 0x2), btcCoopWait (bit 0x10). The smali indexes byte 6 of
    a company-id-included array; bleak hands us the payload with the 2-byte
    company id stripped, so the same byte is payload[4] here (verified against
    real bytes 01c96e6b00 -> clientId 01c96e6b, ad-info 00). It is all in the
    advertisement, so it needs no connection -- which matters because the Windows
    stack connects reliably only right after a radio reset while scanning always
    works. The camera only advertises while *Connect to smart device* is open on
    its screen. Prints a line whenever the bytes change.
    """
    def decode(payload: bytes) -> str:
        if len(payload) < 5:
            return "(zu kurz fuer LSS-Ad-Info)"
        b = payload[4]
        return (f"adInfo=0x{b:02x}  quickWake={(b >> 3) & 1} "
                f"autoTransfer={(b >> 1) & 1} btcCoopWait={(b >> 4) & 1}")

    seen: dict = {}
    print(f"scanning {args.seconds:.0f}s -- Kamera muss im Verbindungsmenue stehen")

    def callback(device, adv) -> None:
        if not any(u.lower() == VENDOR_SERVICE for u in (adv.service_uuids or [])):
            return
        for cid, payload in (adv.manufacturer_data or {}).items():
            key = (cid, bytes(payload))
            if key in seen:
                return
            seen[key] = True
            print(f"  company=0x{cid:04x} data={bytes(payload).hex()}", flush=True)
            print(f"    {decode(bytes(payload))}", flush=True)

    scanner = BleakScanner(detection_callback=callback)
    await scanner.start()
    await asyncio.sleep(args.seconds)
    await scanner.stop()
    if not seen:
        print("  nichts gesehen -- advertisiert die Kamera? (Verbindungsmenue offen?)")


async def cmd_power(args) -> None:
    """Poll POWER_CONTROL (0x2001) and report the wake state as it changes.

    The WiFi path gates on this byte: the vendor app enables the access point
    only when it is not INVALID_WAKE. VALID_WAKE (0x04) is a camera-side state,
    so this watches for the flip while someone changes the camera (leave the
    menu, wake it, start remote photography). Read-only.
    """
    device = await find(args)
    async with BleakClient(device, timeout=args.timeout) as client:
        print(f"connected {device.address}  mtu={client.mtu_size}")
        print("  polling 0x2001 -- change the camera state now (Strg-C beendet)")
        last = None
        deadline = time.monotonic() + args.seconds
        while time.monotonic() < deadline and client.is_connected:
            try:
                value = bytes(await client.read_gatt_char(POWER_UUID))
                code = value[0] if value else 0xFF
                name = POWER_TYPES.get(code, "?")
            except Exception as exc:
                print(f"  read error: {type(exc).__name__}: {str(exc)[:60]}")
                break
            if value != last:
                mark = "  <-- AP moeglich" if name == "VALID_WAKE" else ""
                print(f"  0x2001 = {value.hex()}  {name}{mark}", flush=True)
                last = value
            await asyncio.sleep(args.interval)
        if not client.is_connected:
            print("  ! Verbindung getrennt")


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
            await asyncio.sleep(0.3)
            continue

        # A connection can come up hollow: it reports success, negotiates the
        # minimum MTU of 23 and exposes no services at all. Treat that as a
        # failure -- it is indistinguishable from a working link until the
        # first read fails with "characteristic not found".
        # Two ways a connection comes up useless. It can report success with
        # no services at all, or it can negotiate the bare minimum MTU of 23 --
        # the handshake still squeezes through that, but everything after it
        # behaves badly, and classic bonding then times out. Every run that
        # worked end to end had 515.
        healthy = (
            any(s.uuid.lower() == VENDOR_SERVICE for s in client.services)
            and client.mtu_size > 100
        )
        if not healthy:
            print(
                f"  connect {attempt}/{args.retries}: unusable (mtu={client.mtu_size})",
                file=sys.stderr,
                flush=True,
            )
            await client.disconnect()
            await asyncio.sleep(0.3)
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
POWER_UUID = "00002001-3dd4-4255-8d62-6dc7b9bd5561"
NAME_UUID = "00002002-3dd4-4255-8d62-6dc7b9bd5561"
ESTABLISH_UUID = "00002005-3dd4-4255-8d62-6dc7b9bd5561"
TIME_UUID = "00002006-3dd4-4255-8d62-6dc7b9bd5561"
CONTROL_POINT_UUID = "00002008-3dd4-4255-8d62-6dc7b9bd5561"
FEATURE_UUID = "00002009-3dd4-4255-8d62-6dc7b9bd5561"
CONTROL_FOR_CONTROL_UUID = "00002021-3dd4-4255-8d62-6dc7b9bd5561"

# 0x2021 LSS_CONTROL_POINT_FOR_CONTROL request frame (little-endian):
# [len(2)] [opcode(1)] [reserved(1)] [mode(1)]. RemoteControl = opcode 0x11,
# mode REMOTE_CONTROL=1. The vendor's startRemoteControl sends this and then
# expects POWER_CONTROL to read VALID_WAKE -- so it is the camera's wake trigger.
REMOTE_CONTROL_ON = bytes.fromhex("0500110001")
SERVER_NAME_UUID = "00002003-3dd4-4255-8d62-6dc7b9bd5561"

# 0x2001 POWER_CONTROL is a one-byte enum. WIRE values (field a / getByte in
# BlePowerControlData$Types, NOT the Java ordinals) verified from the smali:
# these are what the camera actually puts on the wire. VALID_WAKE means ready.
# NOTE: 0x03 == VALID_WAKE. An earlier reading here used the ordinals
# (INVALID_WAKE=3) and wrongly flagged the ready camera as not-ready.
POWER_TYPES = {0xFF: "UNDEFINED", 0x00: "STOP", 0x01: "WAKE_WAIT",
               0x02: "INVALID_WAKE", 0x03: "VALID_WAKE"}


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
        log(f"connected  mtu={client.mtu_size}")
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
    """Run the whole four-stage handshake, retrying the whole thing.

    The link drops easily -- reopening the menu on the camera tears down an
    open connection mid-exchange -- and a handshake interrupted after stage 1
    is worthless. So the retry has to wrap the entire sequence, not the
    individual reads.
    """
    attempt = 0
    while True:
        attempt += 1
        try:
            await _pairing_once(args)
            if not args.loop:
                return
            log(f"round {attempt} done; going again")
        except SystemExit:
            if not args.loop:
                raise
            log(f"round {attempt}: camera out of reach, waiting")
        except Exception as exc:
            log(f"round {attempt} broke off: {type(exc).__name__}: {str(exc)[:70]}")
        if not args.loop and attempt >= args.attempts:
            log(f"gave up after {attempt} attempts")
            return
        await asyncio.sleep(1)


async def _pairing_once(args) -> None:
    import nikon_pairing as np

    saved_device = bytes.fromhex(args.device) if args.device else None
    saved_nonce = bytes.fromhex(args.nonce) if args.nonce else None
    stage1 = np.stage_one(saved_device, saved_nonce)
    client = await connect(args)
    async with client:
        log(f"connected  mtu={client.mtu_size}")

        if args.like_app:
            # The vendor app (btsnoop capture, 23.08.) subscribes to
            # notifications on 0x2000 and 0x2008 *before* authenticating -- the
            # camera answers the handshake by notification. Replicate that.
            # NOTE: do NOT call client.pair() here. The camera does no LE pairing
            # (it uses the app-level handshake plus the classic bond); a forced
            # LE pair() drops the link (measured 23.08.). The encryption the app
            # relies on comes from the classic/RFCOMM side, not LE.
            def _notif(short):
                def cb(_char, data):
                    print(f"  NOTIFY {short}  {hexdump(bytes(data))}", flush=True)
                return cb

            for cu, short in ((AUTH_UUID, "2000"), (CONTROL_POINT_UUID, "2008")):
                try:
                    await client.start_notify(cu, _notif(short))
                    print(f"  notify on {short} enabled")
                except Exception as exc:
                    print(f"  notify {short} failed: {type(exc).__name__}: {str(exc)[:50]}")

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

        if args.pairing_json:
            # Everything 'skyshutter wifi' needs to recover the credentials: the
            # three handshake messages and the encrypted 0x2004 blob. Written
            # here, at the one moment we hold an authenticated link.
            import json as _json

            config = bytes(await client.read_gatt_char(f"00002004{VENDOR_SERVICE[8:]}"))
            doc = {
                "stage1": stage1.encode().hex(),
                "stage2": stage2.encode().hex(),
                "stage4": stage4.encode().hex(),
                "config": config.hex(),
            }
            with open(args.pairing_json, "w") as handle:
                _json.dump(doc, handle, indent=2)
            print(f"  -> pairing saved to {args.pairing_json}")
            print(f"     decrypt with:  skyshutter wifi {args.pairing_json}")

        if args.mimic:
            # The order the vendor app uses, taken from the doppelganger's log:
            # write the client name, read the device name, set the clock, read
            # the feature word. Doing it out of order may be why a lone write
            # to 0x2005 did nothing.
            import time as _time

            now = _time.localtime()
            stamp = (
                struct.pack("<H", now.tm_year)
                + bytes([now.tm_mon, now.tm_mday, now.tm_hour, now.tm_min, now.tm_sec])
                + bytes.fromhex("040100")
            )
            log(f"  mimic: clock  {hexdump(stamp)}")
            await client.write_gatt_char(TIME_UUID, stamp, response=True)
            name = bytes(await client.read_gatt_char(SERVER_NAME_UUID))
            log(f"  mimic: 0x2003 {hexdump(name)}")
            feature = bytes(await client.read_gatt_char(FEATURE_UUID))
            log(f"  mimic: 0x2009 {hexdump(feature)}")

        if args.sweep:
            # One byte, on a characteristic whose documented job is exactly
            # this. Read it back after each value and report any change.
            for value in [bytes([v]) for v in (0x00, 0x01, 0x02, 0x04, 0x05, 0x03)]:
                before = bytes(await client.read_gatt_char(ESTABLISH_UUID))
                try:
                    await client.write_gatt_char(ESTABLISH_UUID, value, response=True)
                    verdict = "accepted"
                except Exception as exc:
                    # The ATT error code is the interesting part: "insufficient
                    # authorization" would mean the classic bond is the gate,
                    # while "write not permitted" means the value is simply wrong.
                    verdict = f"refused: {str(exc).splitlines()[0][:70]}"
                await asyncio.sleep(2.5)
                after = bytes(await client.read_gatt_char(ESTABLISH_UUID))
                mark = "  <-- CHANGED" if after != before else ""
                log(f"  0x2005 <- {value.hex()}: {verdict}, now {after.hex()}{mark}")

        if args.wake:
            # Reconstructed from V0.startRemoteControl: write the RemoteControl
            # request to 0x2021, then the camera's POWER_CONTROL (0x2001) should
            # flip from INVALID_WAKE to VALID_WAKE ("wake up and function
            # effective"). This is the wake trigger the plain 0x2005 write lacks.
            try:
                before = bytes(await client.read_gatt_char(POWER_UUID))
                print(f"\n  0x2001 vor Wake  {hexdump(before)}  "
                      f"{POWER_TYPES.get(before[0] if before else 0xFF, '?')}")
                print(f"  0x2021 write     {REMOTE_CONTROL_ON.hex()}  (RemoteControl ON)")
                await client.write_gatt_char(
                    CONTROL_FOR_CONTROL_UUID, REMOTE_CONTROL_ON, response=True
                )
                await asyncio.sleep(1.5)
                after = bytes(await client.read_gatt_char(POWER_UUID))
                name = POWER_TYPES.get(after[0] if after else 0xFF, "?")
                mark = "  <-- geweckt!" if name == "VALID_WAKE" else "  (noch nicht VALID_WAKE)"
                print(f"  0x2001 nach Wake {hexdump(after)}  {name}{mark}")
            except Exception as exc:
                print(f"\n  Wake fehlgeschlagen: {type(exc).__name__}: {str(exc)[:80]}")

        if args.establish:
            payload = bytes.fromhex(args.establish)

            # Reconstructed from the vendor app (CameraConnectByWiFiUseCase):
            # before it writes 0x2005 it clears the LSS control point's
            # ConnectionRequest to OFF and reads the power-control gate, all in
            # the same authenticated session. A lone 0x2005 write skips both --
            # which is the most likely reason ours produced no access point.
            if not args.no_connreq_reset:
                # Faithful replay of the vendor app's M0.a(): 0x2008 is a
                # little-endian short of nibble fields -- bits0-3 TimeRequest,
                # 4-7 LocationRequest, 8-11 ConnectionRequest (OFF=0, ON=1). The
                # app reads it and, *only if* ConnectionRequest is ON, clears that
                # one nibble to OFF and writes it back, leaving Time and Location
                # untouched. If it is already off, the app writes nothing.
                try:
                    cp_before = bytes(await client.read_gatt_char(CONTROL_POINT_UUID))
                    short = int.from_bytes(cp_before[:2], "little") if len(cp_before) >= 2 else 0
                    conn = (short >> 8) & 0xF
                    print(f"\n  0x2008 before  {hexdump(cp_before)}  (ConnectionRequest={conn})")
                    if conn == 1:  # ON -> clear just that nibble, keep the rest
                        new = short & 0x00FF
                        await client.write_gatt_char(
                            CONTROL_POINT_UUID, new.to_bytes(2, "little"), response=True
                        )
                        after = bytes(await client.read_gatt_char(CONTROL_POINT_UUID))
                        print(f"  0x2008 write   {new.to_bytes(2, 'little').hex()}"
                              f"  (ConnectionRequest -> OFF); now {hexdump(after)}")
                    else:
                        print("  0x2008 already not ON -- app writes nothing here, skipping")
                except Exception as exc:
                    print(f"\n  0x2008 not accessible: {type(exc).__name__}: {str(exc)[:70]}")

            try:
                power = bytes(await client.read_gatt_char(POWER_UUID))
                name = POWER_TYPES.get(power[0] if power else 0xFF, "?")
                warn = "  <-- remote shooting UNAVAILABLE" if name == "INVALID_WAKE" else ""
                print(f"  0x2001 power   {hexdump(power)}  {name}{warn}")
            except Exception as exc:
                print(f"  0x2001 not readable: {type(exc).__name__}: {str(exc)[:70]}")

            # The vendor app reads the connection configuration first and only
            # then writes the establishment byte -- it checks there whether the
            # camera has WiFi settings at all. Whether that read is a
            # precondition or just the app being tidy is exactly what we are
            # testing, so do it in the same order.
            config_uuid = f"00002004{VENDOR_SERVICE[8:]}"
            try:
                config = bytes(await client.read_gatt_char(config_uuid))
                flags = config[0] if config else 0
                print(f"\n  0x2004 config  {hexdump(config)}")
                print(f"    flags 0x{flags:02x}: WLAN-Block {'ja' if flags & 1 else 'NEIN'}, "
                      f"BT-Block {'ja' if flags & 2 else 'nein'}")
                if len(config) >= 98:
                    ssid, password = config[1:33], config[33:97]
                    print(f"    SSID-Feld     {'leer' if not any(ssid) else ssid.hex()}")
                    print(f"    Passwort-Feld {'leer' if not any(password) else password.hex()}")
                    print(f"    Verschlüsselung 0x{config[97]:02x}")
            except Exception as exc:
                print(f"\n  0x2004 nicht lesbar: {type(exc).__name__}: {str(exc)[:70]}")

            before = bytes(await client.read_gatt_char(ESTABLISH_UUID))
            print(f"\n  0x2005 before  {hexdump(before)}")
            print(f"  0x2005 write   {hexdump(payload)}")
            try:
                await client.write_gatt_char(ESTABLISH_UUID, payload, response=True)
                print("  -> accepted")
            except Exception as exc:
                print(f"  -> refused: {type(exc).__name__}: {str(exc).splitlines()[0][:90]}")
            await asyncio.sleep(3.0)
            print(f"  0x2005 after   {hexdump(bytes(await client.read_gatt_char(ESTABLISH_UUID)))}")

            # The vendor app stays connected after writing this. If the camera
            # only keeps its access point up while a client is attached, a tool
            # that disconnects straight away would never see it -- so offer to
            # hold the link and watch what happens.
            if args.hold:
                print(f"\n  Verbindung wird {args.hold:.0f}s gehalten — jetzt WLAN scannen.")
                elapsed = 0.0
                while elapsed < args.hold and client.is_connected:
                    await asyncio.sleep(5.0)
                    elapsed += 5.0
                    state = bytes(await client.read_gatt_char(ESTABLISH_UUID))
                    print(f"  +{elapsed:3.0f}s  0x2005 = {state.hex()}", flush=True)
                if not client.is_connected:
                    print("  ! die Kamera hat die Verbindung getrennt")

        # Read everything again: authentication may unlock values that read as
        # zero before, and comparing the two states is the cheapest way to see
        # what the handshake actually bought us. It costs about twenty seconds
        # though, and the camera only stays open for classic bonding briefly
        # after the handshake -- so --quick skips it.
        print("\n  --- values after authenticating ---" if not args.quick else "", end="")
        for service in [] if args.quick else client.services:
            for char in service.characteristics:
                if "read" not in char.properties:
                    continue
                try:
                    value = bytes(await client.read_gatt_char(char))
                except Exception as exc:
                    print(f"  {char.uuid[4:8]}  ERROR {type(exc).__name__}")
                    continue
                print(f"  {char.uuid[4:8]}  {hexdump(value)}")

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
    parser.add_argument(
        "--give-up",
        type=float,
        default=90.0,
        metavar="SEKUNDEN",
        help="Gesamtzeit fuer die Suche, unabhaengig von --retries (Vorgabe 90 s)",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    scan = sub.add_parser("scan", help="list advertising devices")
    scan.add_argument("--seconds", type=float, default=15.0)
    scan.set_defaults(run=cmd_scan)

    sub.add_parser("dump", help="print the GATT tree").set_defaults(run=cmd_dump)
    sub.add_parser("read", help="read every readable characteristic").set_defaults(run=cmd_read)

    adwake = sub.add_parser("adwake", help="watch wake flags from the advertisement (no connect)")
    adwake.add_argument("--seconds", type=float, default=120.0, help="how long to scan")
    adwake.set_defaults(run=cmd_adwake)

    power = sub.add_parser("power", help="poll 0x2001 wake state while you change the camera")
    power.add_argument("--seconds", type=float, default=120.0, help="how long to poll")
    power.add_argument("--interval", type=float, default=2.0, help="seconds between reads")
    power.set_defaults(run=cmd_power)

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
    pairing.add_argument(
        "--pairing-json",
        metavar="PATH",
        help="save the handshake and 0x2004 blob as JSON for 'skyshutter wifi'",
    )
    pairing.add_argument("--seconds", type=float, default=0.0, help="listen afterwards")
    pairing.add_argument(
        "--establish", metavar="HEX", help="write this to 0x2005 after authenticating"
    )
    pairing.add_argument(
        "--hold",
        type=float,
        default=0.0,
        metavar="SEKUNDEN",
        help="nach dem Schreiben so lange verbunden bleiben (fuer den WLAN-Test)"
    )
    pairing.add_argument(
        "--attempts", type=int, default=6, help="restarts of the whole handshake"
    )
    pairing.add_argument(
        "--loop", action="store_true", help="keep going forever; survives every drop"
    )
    pairing.add_argument(
        "--mimic", action="store_true", help="replay the vendor app's post-handshake order"
    )
    pairing.add_argument(
        "--sweep", action="store_true", help="try each plausible value on 0x2005"
    )
    pairing.add_argument(
        "--wake",
        action="store_true",
        help="send RemoteControl on 0x2021 to wake the camera (VALID_WAKE) before --establish",
    )
    pairing.add_argument(
        "--like-app",
        action="store_true",
        help="subscribe notify on 2000+2008 before auth, like the app (no LE pair here)",
    )
    pairing.add_argument(
        "--no-connreq-reset",
        action="store_true",
        help="skip the 0x2008 ConnectionRequest->OFF write before --establish (A/B test)",
    )
    pairing.add_argument(
        "--quick", action="store_true", help="skip the value dump; leaves time for bonding"
    )
    pairing.add_argument("--device", help="reconnect with a known client id (hex)")
    pairing.add_argument("--nonce", help="reconnect with a known client nonce (hex)")
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
