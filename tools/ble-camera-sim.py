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
import struct
import sys
import time
from uuid import UUID

try:
    import winrt.windows.devices.bluetooth.genericattributeprofile as gatt
    from winrt.windows.devices.bluetooth import BluetoothError
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

# What the real camera returned, byte for byte, on 22.08.2026. The serial is a
# placeholder -- pass --serial to use another one.
DEFAULT_SERIAL = "SSSSSSSS"


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


def log(message: str) -> None:
    print(f"{time.strftime('%H:%M:%S')}  {message}", flush=True)


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

    def __init__(self, serial: str, name: str) -> None:
        self.values = initial_values(serial, name)
        self.serial = serial
        self.stage1: np.Message | None = None
        self.salt = 0

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
            self.values[0x2000] = reply.encode()

        elif message.stage == 0x03:
            if self.stage1 is None:
                log("  ! stage 3 without a stage 1")
                return
            expected = np.stage_three_for_salt(self.stage1, self._last_stage2, self.salt)
            ok = message.device + message.nonce == expected.device + expected.nonce
            log(f"  handshake stage 3 in; client answer {'correct' if ok else 'WRONG'}")
            self.values[0x2000] = self._stage_four().encode()
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
        """Stage 4 carries the serial in the device and nonce fields."""
        padded = self.serial.encode("ascii").ljust(8, b"\x00")[:8]
        return np.Message(0x04, bytes(8), padded[:4], padded[4:])

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


def to_bytes(buffer) -> bytes:
    reader = DataReader.from_buffer(buffer)
    return bytes(reader.read_buffer(buffer.length))


def from_bytes(payload: bytes):
    writer = DataWriter()
    writer.write_bytes(list(payload))
    return writer.detach_buffer()


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--serial", default=DEFAULT_SERIAL)
    parser.add_argument("--name", default=None, help="what to report in 0x2003")
    args = parser.parse_args()
    name = args.name or f"P1100_{args.serial}"

    camera = Camera(args.serial, name)

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

        def on_read(sender, event, _uuid=uuid16):
            deferral = event.get_deferral()
            value = camera.read(_uuid)
            log(f"READ  {label(_uuid)}  {hexdump(value)}")
            event.request.respond_with_value(from_bytes(value))
            deferral.complete()

        def on_write(sender, event, _uuid=uuid16):
            deferral = event.get_deferral()
            request = event.request
            camera.write(_uuid, to_bytes(request.value))
            if request.option == gatt.GattWriteOption.WRITE_WITH_RESPONSE:
                request.respond()
            deferral.complete()

        char.add_read_requested(on_read)
        char.add_write_requested(on_write)

    advertising = gatt.GattServiceProviderAdvertisingParameters()
    advertising.is_connectable = True
    advertising.is_discoverable = True
    provider.start_advertising_with_parameters(advertising)

    log(f"advertising {SERVICE_UUID}")
    log(f"reporting as {name!r} in 0x2003")
    log("open the vendor app and look for the camera -- ctrl-c to stop")
    try:
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        provider.stop_advertising()
        log("stopped")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
