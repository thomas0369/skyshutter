"""The camera's BLE GATT database, as measured.

Measured twice on 22.08.2026 and identical both times: first out of a phone's
Bluetooth stack log while the vendor app was paired, then read straight off
the camera over BLE — see docs/FINDINGS.md. It is structure only. Neither
source says what the bytes mean, so this module can say *where* to write and
nothing about *what*.

The camera puts its whole remote-control surface into one vendor service and
numbers the characteristics itself (0x2000, 0x2001, ...). Those numbers are
not Bluetooth SIG assignments; they only mean anything on the vendor base
below. One of them, 0x2a19, collides with the SIG's Battery Level — on the
vendor base it is a different characteristic and must not be read as one.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import IntFlag

#: Suffix every UUID in this service carries. Not the Bluetooth base.
VENDOR_UUID_BASE = "-3dd4-4255-8d62-6dc7b9bd5561"

#: The single vendor service, handles 0x0029..0x0051.
SERVICE_UUID16 = 0xDE00
SERVICE_HANDLE = 0x0029
SERVICE_END_HANDLE = 0x0051

#: Client Characteristic Configuration descriptor, for enabling notify/indicate.
CCCD_UUID16 = 0x2902


class Property(IntFlag):
    """Characteristic property bits, as they appear in the declaration."""

    BROADCAST = 0x01
    READ = 0x02
    WRITE_NO_RESPONSE = 0x04
    WRITE = 0x08
    NOTIFY = 0x10
    INDICATE = 0x20
    SIGNED_WRITE = 0x40
    EXTENDED = 0x80


@dataclass(frozen=True)
class Characteristic:
    """One entry of the vendor service."""

    uuid16: int
    declaration_handle: int
    value_handle: int
    properties: Property

    @property
    def uuid(self) -> str:
        return f"{self.uuid16:08x}{VENDOR_UUID_BASE}"

    @property
    def cccd_handle(self) -> int | None:
        """Handle of this characteristic's CCCD, or None if it has none.

        First derived from the handle gaps in the stack log, then confirmed
        by reading the tree off the camera directly on 22.08.2026: the four
        descriptors sit at 0x002c, 0x003d, 0x004c and 0x0051, one above each
        notify- or indicate-capable value handle.
        """
        if self.properties & (Property.NOTIFY | Property.INDICATE):
            return self.value_handle + 1
        return None

    def can(self, prop: Property) -> bool:
        return bool(self.properties & prop)


def _char(uuid16: int, declaration: int, properties: int) -> Characteristic:
    # The value handle always follows its declaration; that much the log shows.
    return Characteristic(uuid16, declaration, declaration + 1, Property(properties))


#: Measured 22.08.2026, in handle order — first from a phone's stack log, then
#: read off the camera over BLE the same day. Both agree in every field.
#: Absent from the range: 0x200a, 0x2081, 0x2085.
CHARACTERISTICS: tuple[Characteristic, ...] = (
    _char(0x2000, 0x002A, 0x2A),
    _char(0x2001, 0x002D, 0x0A),
    _char(0x2002, 0x002F, 0x08),
    _char(0x2003, 0x0031, 0x02),
    _char(0x2004, 0x0033, 0x0A),
    _char(0x2005, 0x0035, 0x0A),
    _char(0x2006, 0x0037, 0x0A),
    _char(0x2007, 0x0039, 0x08),
    _char(0x2008, 0x003B, 0x1A),
    _char(0x2009, 0x003E, 0x02),
    _char(0x2A19, 0x0040, 0x02),
    _char(0x200B, 0x0042, 0x02),
    _char(0x2080, 0x0044, 0x02),
    _char(0x2082, 0x0046, 0x0A),
    _char(0x2083, 0x0048, 0x08),
    _char(0x2084, 0x004A, 0x22),
    _char(0x2086, 0x004D, 0x02),
    _char(0x2087, 0x004F, 0x2A),
)

_BY_UUID = {c.uuid16: c for c in CHARACTERISTICS}
_BY_VALUE_HANDLE = {c.value_handle: c for c in CHARACTERISTICS}


#: What each characteristic is for.
#:
#: The names come from other people's reverse engineering of the vendor app
#: (see docs/FINDINGS.md) -- read for verification, not copied as code. Four of
#: them we had already established independently from the values this camera
#: returned, and those four agree: 0x2003 held the device name, 0x200b the
#: serial, 0x2006 decoded as the wall clock, and 0x2a19 read 100. That
#: agreement is the reason to trust the rest.
#:
#: "LSS" is the vendor's own prefix for the remote-shutter part of the service.
NAMES: dict[int, str] = {
    0x2000: "authentication",
    0x2001: "power control",
    0x2002: "client device name",
    0x2003: "server device name",
    0x2004: "connection configuration",
    0x2005: "connection establishment",
    0x2006: "current time",
    0x2007: "location information",
    0x2008: "LSS control point",
    0x2009: "LSS feature",
    0x200A: "LSS cable attachment",
    0x200B: "LSS serial number string",
    0x2080: "LSS category info",
    0x2081: "LSS status for capture",
    0x2A19: "battery level",
}

#: Characteristics whose meaning is established, not guessed.
AUTHENTICATION = 0x2000
CLIENT_NAME = 0x2002
NAME = 0x2003
CONNECTION_ESTABLISHMENT = 0x2005
CLOCK = 0x2006
SHUTTER = 0x2008
SERIAL = 0x200B

#: Length of one authentication message on 0x2000. Stage byte, then an 8-byte
#: timestamp, a 4-byte device id and a 4-byte nonce, all little-endian. Matches
#: the 17 zero bytes this camera returns before anyone has authenticated.
AUTH_MESSAGE_LENGTH = 17


def name_of(uuid16: int) -> str:
    """What a characteristic is for, or an empty string if nobody knows."""
    return NAMES.get(uuid16, "")


def decode_clock(raw: bytes) -> datetime:
    """Read the camera's clock out of characteristic 0x2006.

    Ten bytes: a little-endian year, then month, day, hour, minute, second,
    then three bytes whose meaning is unknown. Confirmed once, on 22.08.2026,
    against a value that matched the wall clock to the minute.
    """
    if len(raw) < 7:
        raise ValueError(f"expected at least 7 bytes, got {len(raw)}")
    year = int.from_bytes(raw[0:2], "little")
    month, day, hour, minute, second = raw[2:7]
    return datetime(year, month, day, hour, minute, second)


def decode_text(raw: bytes) -> str:
    """Read one of the padded ASCII fields (0x2003 name, 0x200b serial)."""
    return raw.split(b"\x00", 1)[0].decode("ascii", "replace")


def characteristic(uuid16: int) -> Characteristic:
    """Look up a characteristic by its short vendor UUID."""
    try:
        return _BY_UUID[uuid16]
    except KeyError:
        raise KeyError(f"0x{uuid16:04x} is not in the measured vendor service") from None


def by_value_handle(handle: int) -> Characteristic | None:
    """Name the characteristic a captured handle belongs to, if it is one."""
    return _BY_VALUE_HANDLE.get(handle)


def with_property(prop: Property) -> tuple[Characteristic, ...]:
    """All characteristics carrying a given property bit."""
    return tuple(c for c in CHARACTERISTICS if c.can(prop))
