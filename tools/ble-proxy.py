#!/usr/bin/env python3
"""Sit between the vendor app and the camera and pass every byte through.

The doppelganger (ble-camera-sim.py) has a ceiling: it can answer the
handshake, but it cannot be the camera. The app checks the device name against
what it remembers, and this machine's classic Bluetooth name is its computer
name, which Windows will not let us change. So the app finds a GATT service
that says "camera" and a classic device that says "laptop", and starts over.

A proxy has no such problem. Every answer is the camera's own, so the name, the
serial and the feature bits are right by construction. The classic bonding
happens directly between app and camera and we stay out of it. And the write we
are actually after -- whatever switches the WiFi on -- does not just land in the
log, it reaches the camera and takes effect.

    python tools/ble-proxy.py --transcript proxy.txt

Order matters. We connect to the camera first, which stops it advertising, so
the app can only find us. Open the camera's smart-device menu, start this, then
open the app.

Everything written to the camera here comes from the vendor's own app. This
tool does not invent traffic.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
import time
from uuid import UUID

try:
    from bleak import BleakClient, BleakScanner
except ImportError:  # pragma: no cover - bench tool
    sys.exit("bleak is missing: pip install bleak")

try:
    import winrt.windows.devices.bluetooth.genericattributeprofile as gatt
    from winrt.windows.devices.bluetooth import BluetoothError
    from winrt.windows.foundation import AsyncStatus
    from winrt.windows.storage.streams import DataReader, DataWriter
except ImportError:  # pragma: no cover - bench tool
    sys.exit("needs the Windows Python with the winrt packages")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import nikon_pairing as np

VENDOR_BASE = "-3dd4-4255-8d62-6dc7b9bd5561"
SERVICE_UUID = UUID("0000de00" + VENDOR_BASE)
VENDOR_SERVICE = str(SERVICE_UUID)

READ = gatt.GattCharacteristicProperties.READ
WRITE = gatt.GattCharacteristicProperties.WRITE
NOTIFY = gatt.GattCharacteristicProperties.NOTIFY
INDICATE = gatt.GattCharacteristicProperties.INDICATE

NAMES = {
    0x2000: "AUTHENTICATION",
    0x2001: "POWER_CONTROL",
    0x2002: "CLIENT_DEVICE_NAME",
    0x2003: "SERVER_DEVICE_NAME",
    0x2004: "CONNECTION_CONFIGURATION",
    0x2005: "CONNECTION_ESTABLISHMENT",
    0x2006: "CURRENT_TIME",
    0x2007: "LOCATION_INFORMATION",
    0x2008: "LSS_CONTROL_POINT",
    0x2009: "LSS_FEATURE",
    0x200B: "LSS_SERIAL_NUMBER_STRING",
    0x2080: "LSS_CATEGORY_INFO",
    0x2A19: "BATTERY_LEVEL",
}

#: Writes to these are the ones we are hunting: one of them turns the WiFi on.
INTERESTING = {0x2004, 0x2005, 0x2007, 0x2082, 0x2083, 0x2087}

TRANSCRIPT = None


def log(message: str) -> None:
    line = f"{time.strftime('%H:%M:%S')}  {message}"
    print(line, flush=True)
    if TRANSCRIPT is not None:
        TRANSCRIPT.write(line + "\n")
        TRANSCRIPT.flush()


def hexdump(data: bytes) -> str:
    text = "".join(chr(c) if 32 <= c < 127 else "." for c in data)
    return f"{len(data):3}B  {data.hex()}  |{text}|"


def label(uuid16: int) -> str:
    return f"0x{uuid16:04x} {NAMES.get(uuid16, '')}".rstrip()


def short(uuid: str) -> int:
    return int(uuid[4:8], 16)


def to_bytes(buffer) -> bytes:
    return bytes(DataReader.from_buffer(buffer).read_buffer(buffer.length))


def from_bytes(payload: bytes):
    writer = DataWriter()
    writer.write_bytes(payload)
    return writer.detach_buffer()


def block(operation, timeout: float = 3.0):
    """Wait out a WinRT operation from a plain thread."""
    deadline = time.monotonic() + timeout
    while operation.status == AsyncStatus.STARTED and time.monotonic() < deadline:
        time.sleep(0.001)
    return operation.get_results()


async def subscribe_all(proxy, camera: BleakClient) -> None:
    """Listen on everything the camera can push, so nothing it says is lost."""
    service = next(s for s in camera.services if s.uuid.lower() == VENDOR_SERVICE)
    for char in service.characteristics:
        if "notify" not in char.properties and "indicate" not in char.properties:
            continue
        uuid16 = short(char.uuid)

        def handler(_sender, data, _uuid=uuid16):
            proxy.on_notify(_uuid, bytes(data))

        try:
            await camera.start_notify(char.uuid, handler)
            log(f"  subscribed to the camera's {label(uuid16)}")
        except Exception as exc:
            log(f"  cannot subscribe {label(uuid16)}: {str(exc)[:70]}")


async def connect_camera(retries: int, timeout: float) -> BleakClient:
    """Grab the camera before the app can, and check the link is real."""

    def matches(device, adv) -> bool:
        return any(u.lower() == VENDOR_SERVICE for u in adv.service_uuids)

    for attempt in range(1, retries + 1):
        device = await BleakScanner.find_device_by_filter(matches, timeout=timeout)
        if device is None:
            log(f"  scan {attempt}/{retries}: camera silent (is its menu open?)")
            continue
        client = BleakClient(device, timeout=timeout)
        try:
            await client.connect()
        except Exception as exc:
            log(f"  connect {attempt}/{retries}: {type(exc).__name__}")
            continue
        # Same trap as everywhere else: a link can come up with no services or
        # the minimum MTU and behave badly from then on.
        healthy = (
            any(s.uuid.lower() == VENDOR_SERVICE for s in client.services)
            and client.mtu_size > 100
        )
        if not healthy:
            log(f"  connect {attempt}/{retries}: unusable (mtu={client.mtu_size})")
            await client.disconnect()
            continue
        log(f"camera connected, mtu={client.mtu_size} -- it has stopped advertising")
        return client
    sys.exit("could not reach the camera; open its smart-device menu and retry")


class Proxy:
    """Passes reads, writes and notifications between the two sides."""

    def __init__(self, camera: BleakClient, loop: asyncio.AbstractEventLoop) -> None:
        self.camera = camera
        self.loop = loop
        self.locals: dict[int, object] = {}
        #: Set while we run our own handshake, so its answers do not get
        #: forwarded to an app that is not there yet.
        self.pending: asyncio.Future | None = None

    async def authenticate(self, device: bytes, nonce: bytes) -> bool:
        """Hold the link by doing what the camera waits for.

        Measured: an unauthenticated client is dropped after about eight
        seconds. A proxy that only listens therefore never survives long enough
        for the app to arrive. Running the reconnect handshake with the
        identity from our own pairing keeps the link up.
        """
        stage1 = np.stage_one(device, nonce)
        reply = await self.exchange(stage1.encode())
        if reply is None:
            return False
        stage2 = np.Message.decode(reply)
        try:
            salt = np.find_salt(stage1, stage2)
            stage3 = np.stage_three_for_salt(stage1, stage2, salt)
        except np.HandshakeError as exc:
            log(f"! handshake failed: {exc}")
            return False
        final = await self.exchange(stage3.encode())
        if final is None:
            return False
        log(f"authenticated with the camera (salt #{salt}); the link will stay up")
        return True

    async def exchange(self, payload: bytes, timeout: float = 6.0) -> bytes | None:
        """Write a handshake stage and wait for the camera's indication."""
        self.pending = self.loop.create_future()
        await self.camera.write_gatt_char(self.char_uuid(0x2000), payload, response=True)
        try:
            return await asyncio.wait_for(self.pending, timeout)
        except asyncio.TimeoutError:
            log("! the camera did not answer the handshake")
            return None
        finally:
            self.pending = None

    # The GATT server handlers run on WinRT threads with no event loop, and
    # bleak needs ours. Hand the work over and wait for it -- blocking here is
    # correct: the app is waiting for the camera's answer anyway.
    def call(self, coro, timeout: float = 5.0):
        return asyncio.run_coroutine_threadsafe(coro, self.loop).result(timeout)

    def on_read(self, uuid16: int) -> bytes:
        try:
            value = bytes(self.call(self.camera.read_gatt_char(self.char_uuid(uuid16))))
        except Exception as exc:
            log(f"! read {label(uuid16)} from camera failed: {type(exc).__name__}: {exc}")
            return b""
        log(f"READ  {label(uuid16)}  {hexdump(value)}")
        return value

    def on_write(self, uuid16: int, payload: bytes) -> None:
        mark = "  <<< CANDIDATE" if uuid16 in INTERESTING else ""
        log(f"WRITE {label(uuid16)}{mark}")
        log(f"      {hexdump(payload)}")
        try:
            self.call(
                self.camera.write_gatt_char(self.char_uuid(uuid16), payload, response=True)
            )
        except Exception as exc:
            log(f"! write {label(uuid16)} to camera failed: {type(exc).__name__}: {exc}")

    def on_notify(self, uuid16: int, payload: bytes) -> None:
        """The camera said something unprompted; hand it to the app."""
        log(f"NOTIFY {label(uuid16)}  {hexdump(payload)}")
        if uuid16 == 0x2000 and self.pending is not None and not self.pending.done():
            self.pending.set_result(payload)
            return
        char = self.locals.get(uuid16)
        if char is None:
            return
        clients = len(char.subscribed_clients)
        if not clients:
            log("  (no subscriber on our side, dropped)")
            return
        try:
            block(char.notify_value_async(from_bytes(payload)))
        except Exception as exc:
            log(f"  ! forwarding failed: {type(exc).__name__}: {exc}")

    @staticmethod
    def char_uuid(uuid16: int) -> str:
        return f"{uuid16:08x}{VENDOR_BASE}"


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--retries", type=int, default=40)
    parser.add_argument("--timeout", type=float, default=6.0)
    parser.add_argument("--transcript", default=None)
    # Measured 22.08.2026: authenticating here makes the camera reject the
    # app's own handshake with error 0x80 -- it takes one per connection. The
    # keepalive reads hold the link on their own, so leave this alone unless
    # something else needs the proxy to be a paired client.
    parser.add_argument("--device", help="authenticate as this identity; blocks the app")
    parser.add_argument("--nonce", help="the nonce that goes with it, hex")
    parser.add_argument(
        "--keepalive",
        type=float,
        default=3.0,
        help="read the clock this often to keep the camera from hanging up; 0 disables",
    )
    args = parser.parse_args()

    if args.transcript:
        global TRANSCRIPT
        TRANSCRIPT = open(args.transcript, "a", encoding="utf-8")

    camera = await connect_camera(args.retries, args.timeout)
    proxy = Proxy(camera, asyncio.get_running_loop())
    await subscribe_all(proxy, camera)

    # An unauthenticated client is dropped after eight seconds, so this has to
    # happen before anything else -- otherwise the app arrives to find a proxy
    # whose upstream is already gone.
    if args.device and args.nonce:
        log("! authenticating: the app's own handshake will be refused with 0x80")
        await proxy.authenticate(bytes.fromhex(args.device), bytes.fromhex(args.nonce))

    # Mirror the camera's own layout rather than a hardcoded table: whatever it
    # offers is what the app gets to see.
    service = next(s for s in camera.services if s.uuid.lower() == VENDOR_SERVICE)
    layout = []
    for char in service.characteristics:
        props = 0
        for name, flag in (
            ("read", READ),
            ("write", WRITE),
            ("notify", NOTIFY),
            ("indicate", INDICATE),
        ):
            if name in char.properties:
                props |= flag
        layout.append((short(char.uuid), props))
    log(f"mirroring {len(layout)} characteristics")

    result = await gatt.GattServiceProvider.create_async(SERVICE_UUID)
    if result.error != BluetoothError.SUCCESS:
        return f"could not create the service: {result.error}"
    provider = result.service_provider

    for uuid16, props in layout:
        params = gatt.GattLocalCharacteristicParameters()
        params.characteristic_properties = props
        char_result = await provider.service.create_characteristic_async(
            UUID(Proxy.char_uuid(uuid16)), params
        )
        if char_result.error != BluetoothError.SUCCESS:
            log(f"! {label(uuid16)} failed: {char_result.error}")
            continue
        local = char_result.characteristic

        def on_read(sender, event, _uuid=uuid16):
            deferral = event.get_deferral()
            try:
                request = block(event.get_request_async())
                request.respond_with_value(from_bytes(proxy.on_read(_uuid)))
            except Exception as exc:
                log(f"! serving read {label(_uuid)}: {type(exc).__name__}: {exc}")
            finally:
                deferral.complete()

        def on_write(sender, event, _uuid=uuid16):
            deferral = event.get_deferral()
            try:
                request = block(event.get_request_async())
                proxy.on_write(_uuid, to_bytes(request.value))
                if request.option == gatt.GattWriteOption.WRITE_WITH_RESPONSE:
                    request.respond()
            except Exception as exc:
                log(f"! serving write {label(_uuid)}: {type(exc).__name__}: {exc}")
            finally:
                deferral.complete()

        def on_subscribers(sender, _args, _uuid=uuid16):
            log(f"SUBSCRIBE {label(_uuid)}: {len(sender.subscribed_clients)} client(s)")

        local.add_read_requested(on_read)
        local.add_write_requested(on_write)
        local.add_subscribed_clients_changed(on_subscribers)
        proxy.locals[uuid16] = local

    advertising = gatt.GattServiceProviderAdvertisingParameters()
    advertising.is_connectable = True
    advertising.is_discoverable = True
    provider.start_advertising_with_parameters(advertising)
    log("advertising as the camera -- open the app now, ctrl-c to stop")

    # The camera drops the link for reasons of its own -- a closed menu, a
    # timeout, a mood. Rebuilding the upstream while the app keeps talking to
    # our unchanged GATT server is better than ending the session.
    # Even an authenticated client gets dropped after about nine seconds if it
    # goes quiet. A periodic read is the cheapest traffic there is, and the
    # clock is a value the app reads anyway.
    async def keepalive() -> None:
        while True:
            await asyncio.sleep(args.keepalive)
            if not proxy.camera.is_connected:
                continue
            try:
                await proxy.camera.read_gatt_char(Proxy.char_uuid(0x2006))
            except Exception:
                pass

    task = asyncio.create_task(keepalive()) if args.keepalive else None

    try:
        while True:
            await asyncio.sleep(1)
            if proxy.camera.is_connected:
                continue
            log("! the camera dropped the link -- reconnecting")
            try:
                proxy.camera = await connect_camera(args.retries, args.timeout)
                await subscribe_all(proxy, proxy.camera)
                if args.device and args.nonce:
                    await proxy.authenticate(
                        bytes.fromhex(args.device), bytes.fromhex(args.nonce)
                    )
            except SystemExit:
                log("! could not get the camera back")
                break
    except KeyboardInterrupt:
        pass
    finally:
        if task is not None:
            task.cancel()
        provider.stop_advertising()
        if proxy.camera.is_connected:
            await proxy.camera.disconnect()
        log("stopped")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
