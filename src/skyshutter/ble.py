"""The camera's BLE GATT database, as measured.

Everything in this module was read out of a phone's Bluetooth stack log while
the vendor app was paired with the camera on 22.08.2026 — see
docs/FINDINGS.md. It is structure only: the log records which handles and
UUIDs exist, never the bytes that travelled over them. So this module can say
*where* to write, and says nothing about *what* to write.

The camera puts its whole remote-control surface into one vendor service and
numbers the characteristics itself (0x2000, 0x2001, ...). Those numbers are
not Bluetooth SIG assignments; they only mean anything on the vendor base
below. One of them, 0x2a19, collides with the SIG's Battery Level — on the
vendor base it is a different characteristic and must not be read as one.
"""

from __future__ import annotations

from dataclasses import dataclass
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

        Derived, not measured: the log lists characteristics but not their
        descriptors. Exactly the four notify/indicate-capable entries are
        followed by an unaccounted-for handle, and each gap sits directly
        after the value handle — which is where a CCCD belongs. A capture
        with payloads would confirm it; until then treat this as a good
        first guess, not a measurement.
        """
        if self.properties & (Property.NOTIFY | Property.INDICATE):
            return self.value_handle + 1
        return None

    def can(self, prop: Property) -> bool:
        return bool(self.properties & prop)


def _char(uuid16: int, declaration: int, properties: int) -> Characteristic:
    # The value handle always follows its declaration; that much the log shows.
    return Characteristic(uuid16, declaration, declaration + 1, Property(properties))


#: Measured 22.08.2026, in handle order. Absent from the range: 0x200a,
#: 0x2081, 0x2085 — the camera does not expose them, or not in this state.
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
