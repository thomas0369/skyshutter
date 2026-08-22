#!/usr/bin/env python3
"""Pretend to be the camera, so the vendor app talks to us instead.

The camera will not tell us how its WiFi gets switched on. The app knows, and
if it believes it is talking to a camera it will say so. So we put up the same
GATT service the camera advertises, hand back the values we measured off the
real one, and answer the authentication handshake -- which we can compute, not
just verify. Then we log every byte the app sends.

Runs on the Windows Python against the built-in adapter; WSL has no Bluetooth.
Windows will not let us set the advertised name, so we advertise the service
UUID and put the real name in 0x2003 (SERVER_DEVICE_NAME), where the app reads
it from. Whether that is enough is exactly what this experiment answers.

    python tools/ble-camera-sim.py
    python tools/ble-camera-sim.py --serial 12345678

Nothing here touches the real camera.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import platform
import struct
import sys
import time
from uuid import UUID

try:
    import winrt.windows.devices.bluetooth.genericattributeprofile as gatt
    from winrt.windows.devices.bluetooth import BluetoothError
    from winrt.windows.devices.bluetooth.rfcomm import RfcommServiceId, RfcommServiceProvider
    from winrt.windows.foundation import AsyncStatus
    from winrt.windows.networking.sockets import SocketProtectionLevel, StreamSocketListener
    from winrt.windows.storage.streams import DataReader, DataWriter
except ImportError:  # pragma: no cover - bench tool
    sys.exit("needs the Windows Python with the winrt packages (pip install winrt-runtime)")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import nikon_pairing as np

VENDOR_BASE = "-3dd4-4255-8d62-6dc7b9bd5561"
SERVICE_UUID = UUID("0000de00" + VENDOR_BASE)

READ = gatt.GattCharacteristicProperties.READ
WRITE = gatt.GattCharacteristicProperties.WRITE
NOTIFY = gatt.GattCharacteristicProperties.NOTIFY
INDICATE = gatt.GattCharacteristicProperties.INDICATE

# What the real camera returned, byte for byte, on 22.08.2026 -- except the
# serial, which is a placeholder on purpose: the real one identifies the device
# and this repository is public. Pass --serial and --auth-serial to use it.
DEFAULT_SERIAL = "00000000"


def initial_values(serial: str, name: str) -> dict[int, bytes]:
    """The state a freshly woken camera presents."""
    return {
        0x2000: bytes(17),  # authentication, all zero until a handshake runs
        0x2001: b"\x03",  # power control
        0x2002: b"",  # client device name, write only
        0x2003: name.encode("ascii").ljust(32, b"\x00"),
        0x2004: b"\x03" + bytes(96) + bytes.fromhex("03ef010000"),
        0x2005: b"\x03",  # connection establishment
        0x2006: b"",  # current time, filled in per read
        0x2007: b"",  # location, write only
        0x2008: bytes.fromhex("1100"),  # LSS control point
        0x2009: bytes.fromhex("fd010000"),  # LSS feature
        0x2A19: b"\x64",  # battery level, 100
        0x200B: serial.encode("ascii").ljust(33, b"\x00"),
        0x2080: bytes.fromhex("03000000"),
        0x2082: bytes.fromhex("020203030f0f1111121213131414282829292020212100000000000000000000"),
        0x2083: b"",  # write only
        0x2084: bytes(6),
        0x2086: bytes.fromhex("03000000"),
        0x2087: bytes(17),
    }


# uuid16 -> properties, in the order the real camera lists them.
LAYOUT: tuple[tuple[int, int], ...] = (
    (0x2000, READ | WRITE | INDICATE),
    (0x2001, READ | WRITE),
    (0x2002, WRITE),
    (0x2003, READ),
    (0x2004, READ | WRITE),
    (0x2005, READ | WRITE),
    (0x2006, READ | WRITE),
    (0x2007, WRITE),
    (0x2008, READ | WRITE | NOTIFY),
    (0x2009, READ),
    (0x2A19, READ),
    (0x200B, READ),
    (0x2080, READ),
    (0x2082, READ | WRITE),
    (0x2083, WRITE),
    (0x2084, READ | INDICATE),
    (0x2086, READ),
    (0x2087, READ | WRITE | INDICATE),
)

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


#: Everything also goes here, so a long session is not lost to a scrollback.
TRANSCRIPT: object | None = None


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


def clock_bytes() -> bytes:
    """0x2006 as the camera formats it: LE year, then the fields, then three unknowns."""
    now = time.localtime()
    return (
        struct.pack("<H", now.tm_year)
        + bytes([now.tm_mon, now.tm_mday, now.tm_hour, now.tm_min, now.tm_sec])
        + bytes.fromhex("040100")
    )


class Camera:
    """The state our doppelganger keeps while the app talks to it."""

    def __init__(self, serial: str, name: str, auth_serial: bytes | None = None) -> None:
        self.values = initial_values(serial, name)
        self.serial = serial
        # Stage 4 does not carry the printed serial. The real camera answered
        # 3230303130325160 -- "200102" followed by two bytes that are not ASCII
        # at all. The app remembers this value and rejects a camera that gives a
        # different one, so guessing it from the printed number is not enough.
        self.auth_serial = auth_serial or serial.encode("ascii").ljust(8, b"\x00")[:8]
        self.stage1: np.Message | None = None
        self.salt = 0
        self.characteristics: dict[int, object] = {}

    def push(self, uuid16: int, value: bytes) -> None:
        """Send a value out, rather than waiting to be read.

        0x2000 is indicate-capable and the app never reads it back -- it waits
        to be told. Storing the answer is not enough; it has to be pushed.
        """
        self.values[uuid16] = value
        char = self.characteristics.get(uuid16)
        if char is None:
            return
        clients = len(char.subscribed_clients)
        if not clients:
            log(f"  (nobody subscribed to {label(uuid16)}, cannot push)")
            return
        try:
            block(char.notify_value_async(from_bytes(value)), timeout=3.0)
            log(f"  -> pushed {hexdump(value)} to {clients} subscriber(s)")
        except Exception as exc:
            log(f"  ! push failed: {type(exc).__name__}: {exc}")

    # --- the handshake, from the camera's side ------------------------------

    def on_authentication(self, payload: bytes) -> None:
        """Answer whichever handshake stage the app just sent."""
        if len(payload) != np.MESSAGE_LENGTH:
            log(f"  ! authentication message has {len(payload)} bytes, expected 17")
            return
        message = np.Message.decode(payload)

        if message.stage == 0x01:
            self.stage1 = message
            self.salt = int.from_bytes(os.urandom(1), "big") % len(np.SALTS)
            reply = self._stage_two(message)
            log(f"  handshake stage 1 in; answering with stage 2, salt #{self.salt}")
            self.push(0x2000, reply.encode())

        elif message.stage == 0x03:
            if self.stage1 is None:
                log("  ! stage 3 without a stage 1")
                return
            expected = np.stage_three_for_salt(self.stage1, self._last_stage2, self.salt)
            ok = message.device + message.nonce == expected.device + expected.nonce
            log(f"  handshake stage 3 in; client answer {'correct' if ok else 'WRONG'}")
            self.push(0x2000, self._stage_four().encode())
            if ok:
                log("  -> app is now authenticated")
        else:
            log(f"  ! unexpected handshake stage 0x{message.stage:02x}")

    def _stage_two(self, stage1: np.Message) -> np.Message:
        """Our challenge: hash our timestamp and theirs under the chosen salt."""
        stamp = os.urandom(8)
        stage2 = np.Message(0x02, stamp, bytes(4), bytes(4))
        salt_a, salt_b = np.SALTS[self.salt]
        cam_lo, cam_hi = stage2.halves
        our_lo, our_hi = stage1.halves
        left, right = np.blowfish_hash([salt_a, salt_b, cam_lo, cam_hi, our_lo, our_hi])
        self._last_stage2 = np.Message(
            0x02, stamp, struct.pack(">I", left), struct.pack(">I", right)
        )
        return self._last_stage2

    def _stage_four(self) -> np.Message:
        """Stage 4 carries the internal serial in the device and nonce fields."""
        return np.Message(0x04, bytes(8), self.auth_serial[:4], self.auth_serial[4:8])

    # --- reads and writes ---------------------------------------------------

    def read(self, uuid16: int) -> bytes:
        if uuid16 == 0x2006:
            return clock_bytes()
        return self.values.get(uuid16, b"")

    def write(self, uuid16: int, payload: bytes) -> None:
        log(f"WRITE {label(uuid16)}")
        log(f"      {hexdump(payload)}")
        if uuid16 == 0x2000:
            self.on_authentication(payload)
            return
        self.values[uuid16] = payload
        if uuid16 == 0x2002:
            client = payload.split(b"\x00", 1)[0].decode("ascii", "replace")
            log(f"  -> app registered itself as {client!r}")
        elif uuid16 == 0x2005:
            log("  *** CONNECTION_ESTABLISHMENT -- this is the WiFi trigger ***")
        elif uuid16 == 0x2008:
            log("  *** LSS_CONTROL_POINT -- shutter or remote command ***")


async def become_findable() -> object | None:
    """Make this machine findable over *classic* Bluetooth, and listen.

    The BLE half is only the first act. Measured on the real camera: the client
    then drops the link, runs a classic inquiry and bonds -- and only that bond
    registers it. A doppelganger that offers BLE alone therefore leaves the app
    hanging exactly where we hung yesterday.

    Windows is not discoverable on its own; it becomes discoverable while a
    service asks for it, which is what start_advertising_with_radio_discoverability
    does. The serial port we put up is also the channel the app may try to open
    afterwards, so anything it says there lands in the log.
    """
    provider = await RfcommServiceProvider.create_async(RfcommServiceId.serial_port)
    listener = StreamSocketListener()
    sockets: list = []

    def on_connection(sender, event):
        sockets.append(event.socket)
        host = event.socket.information.remote_host_name
        log(f"*** CLASSIC CONNECT from {host.display_name if host else '?'} ***")

    listener.add_connection_received(on_connection)
    await listener.bind_service_name_with_protection_level_async(
        provider.service_id.as_string(), SocketProtectionLevel.PLAIN_SOCKET
    )
    provider.start_advertising_with_radio_discoverability(listener, True)
    log("classic Bluetooth: discoverable, serial port offered")
    return provider, sockets


async def drain(sockets: list) -> None:
    """Log whatever arrives on a classic connection."""
    for socket in list(sockets):
        reader = DataReader(socket.input_stream)
        reader.input_stream_options = 1  # partial: hand back what is there
        try:
            count = await reader.load_async(4096)
        except Exception as exc:
            log(f"classic read failed: {type(exc).__name__}: {str(exc)[:70]}")
            sockets.remove(socket)
            continue
        if count:
            log(f"CLASSIC RECV {hexdump(bytes(reader.read_buffer(count)))}")


def block(operation, timeout: float = 2.0):
    """Wait for a WinRT async operation from a plain thread.

    These handlers run on a WinRT callback thread with no event loop, so
    asyncio is no help -- and the operation is normally finished before we
    even look. Spin briefly and take the result.
    """
    deadline = time.monotonic() + timeout
    while operation.status == AsyncStatus.STARTED and time.monotonic() < deadline:
        time.sleep(0.001)
    return operation.get_results()


def to_bytes(buffer) -> bytes:
    reader = DataReader.from_buffer(buffer)
    return bytes(reader.read_buffer(buffer.length))


def from_bytes(payload: bytes):
    writer = DataWriter()
    writer.write_bytes(payload)
    return writer.detach_buffer()


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--serial", default=DEFAULT_SERIAL)
    parser.add_argument("--name", default=None, help="what to report in 0x2003")
    parser.add_argument(
        "--host-name",
        action="store_true",
        help="report this machine's own name in 0x2003 instead of a camera name",
    )
    parser.add_argument(
        "--ble-only",
        action="store_true",
        help="skip the classic side; the app will then hang after the handshake",
    )
    parser.add_argument("--transcript", default=None, help="also write the log to this file")
    parser.add_argument(
        "--auth-serial",
        default=None,
        metavar="HEX",
        help="the 8 bytes stage 4 answers with; the real camera's are not all ASCII",
    )
    args = parser.parse_args()

    if args.transcript:
        global TRANSCRIPT
        TRANSCRIPT = open(args.transcript, "a", encoding="utf-8")
    # After the BLE handshake the client drops the link and hunts for a
    # *classic* Bluetooth device whose name matches -- the reference
    # implementation compares it verbatim. Windows takes its Bluetooth name
    # from the computer name and will not let us change it, so the way to be
    # findable is to answer with that name here.
    if args.host_name:
        name = os.environ.get("COMPUTERNAME") or platform.node()
    else:
        name = args.name or f"P1100_{args.serial}"

    auth_serial = bytes.fromhex(args.auth_serial) if args.auth_serial else None
    if auth_serial is not None and len(auth_serial) != 8:
        return "--auth-serial needs exactly 8 bytes (16 hex digits)"
    camera = Camera(args.serial, name, auth_serial)

    result = await gatt.GattServiceProvider.create_async(SERVICE_UUID)
    if result.error != BluetoothError.SUCCESS:
        return f"could not create the service: {result.error}"
    provider = result.service_provider

    for uuid16, props in LAYOUT:
        params = gatt.GattLocalCharacteristicParameters()
        params.characteristic_properties = props
        char_result = await provider.service.create_characteristic_async(
            UUID(f"{uuid16:08x}{VENDOR_BASE}"), params
        )
        if char_result.error != BluetoothError.SUCCESS:
            log(f"! {label(uuid16)} failed: {char_result.error}")
            continue
        char = char_result.characteristic

        # The request only arrives via an async call, and these handlers run on
        # a WinRT thread with no event loop of its own -- hence asyncio.run.
        def on_read(sender, event, _uuid=uuid16):
            deferral = event.get_deferral()
            try:
                request = block(event.get_request_async())
                value = camera.read(_uuid)
                log(f"READ  {label(_uuid)}  {hexdump(value)}")
                request.respond_with_value(from_bytes(value))
            except Exception as exc:
                log(f"! read {label(_uuid)} failed: {type(exc).__name__}: {exc}")
            finally:
                deferral.complete()

        def on_write(sender, event, _uuid=uuid16):
            deferral = event.get_deferral()
            try:
                request = block(event.get_request_async())
                camera.write(_uuid, to_bytes(request.value))
                if request.option == gatt.GattWriteOption.WRITE_WITH_RESPONSE:
                    request.respond()
            except Exception as exc:
                log(f"! write {label(_uuid)} failed: {type(exc).__name__}: {exc}")
            finally:
                deferral.complete()

        def on_subscribers(sender, _args, _uuid=uuid16):
            log(f"SUBSCRIBE {label(_uuid)}: {len(sender.subscribed_clients)} client(s)")

        char.add_read_requested(on_read)
        char.add_write_requested(on_write)
        char.add_subscribed_clients_changed(on_subscribers)
        camera.characteristics[uuid16] = char

    advertising = gatt.GattServiceProviderAdvertisingParameters()
    advertising.is_connectable = True
    advertising.is_discoverable = True
    provider.start_advertising_with_parameters(advertising)

    log(f"advertising {SERVICE_UUID}")
    log(f"reporting as {name!r} in 0x2003")

    rfcomm, sockets = None, []
    if not args.ble_only:
        try:
            rfcomm, sockets = await become_findable()
        except Exception as exc:
            log(f"! classic Bluetooth stayed off: {type(exc).__name__}: {exc}")
            log("  the app will complete the handshake and then hang -- see docs/pairing.md")

    log("open the vendor app and look for the camera -- ctrl-c to stop")
    try:
        while True:
            await asyncio.sleep(0.5)
            if sockets:
                await drain(sockets)
    except KeyboardInterrupt:
        provider.stop_advertising()
        if rfcomm is not None:
            rfcomm.stop_advertising()
        log("stopped")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
