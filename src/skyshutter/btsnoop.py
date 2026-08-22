"""Read Android btsnoop_hci.log files and decode the ATT/GATT traffic in them.

Why this exists: the camera hands its WiFi credentials to the phone over
Bluetooth before the WiFi session starts. That handover is the missing half of
the protocol, and it is only visible in a Bluetooth capture.

Wireshark decodes these files too. This module exists anyway because it can do
two things Wireshark will not: hunt a capture for the strings that look like
WiFi credentials, and redact them on the way out, so a capture can be discussed
in a public repository without leaking the passphrase.

Format references:
  btsnoop file format  — Wireshark wiki / RFC 1761 derivative
  Bluetooth Core Spec  — Vol 3 Part F (ATT), Vol 4 Part E (HCI)
"""

from __future__ import annotations

import re
import struct
import zipfile
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path

BTSNOOP_MAGIC = b"btsnoop\x00"

# Microseconds between 0000-01-01 (btsnoop's epoch) and 1970-01-01.
BTSNOOP_EPOCH_DELTA_US = 0x00DCDDB30F2F8000

# Datalink types seen in the wild. Android writes 1002.
DATALINK_HCI_UNENCAP = 1001
DATALINK_HCI_UART = 1002

H4_COMMAND = 0x01
H4_ACL = 0x02
H4_SCO = 0x03
H4_EVENT = 0x04

L2CAP_CID_ATT = 0x0004
L2CAP_CID_LE_SIGNALING = 0x0005
L2CAP_CID_SMP = 0x0006

ATT_OPCODES = {
    0x01: "Error Response",
    0x02: "Exchange MTU Request",
    0x03: "Exchange MTU Response",
    0x04: "Find Information Request",
    0x05: "Find Information Response",
    0x06: "Find By Type Value Request",
    0x07: "Find By Type Value Response",
    0x08: "Read By Type Request",
    0x09: "Read By Type Response",
    0x0A: "Read Request",
    0x0B: "Read Response",
    0x0C: "Read Blob Request",
    0x0D: "Read Blob Response",
    0x0E: "Read Multiple Request",
    0x0F: "Read Multiple Response",
    0x10: "Read By Group Type Request",
    0x11: "Read By Group Type Response",
    0x12: "Write Request",
    0x13: "Write Response",
    0x16: "Prepare Write Request",
    0x17: "Prepare Write Response",
    0x18: "Execute Write Request",
    0x19: "Execute Write Response",
    0x1B: "Handle Value Notification",
    0x1D: "Handle Value Indication",
    0x1E: "Handle Value Confirmation",
    0x52: "Write Command",
    0xD2: "Signed Write Command",
}

# Only the SIG-assigned UUIDs we can name without guessing. Everything else the
# decoder learns from the capture's own service discovery.
KNOWN_UUIDS = {
    0x1800: "Generic Access",
    0x1801: "Generic Attribute",
    0x180A: "Device Information",
    0x180F: "Battery Service",
    0x2800: "Primary Service",
    0x2801: "Secondary Service",
    0x2802: "Include",
    0x2803: "Characteristic",
    0x2901: "Characteristic User Description",
    0x2902: "Client Characteristic Configuration",
    0x2A00: "Device Name",
    0x2A01: "Appearance",
    0x2A19: "Battery Level",
    0x2A24: "Model Number",
    0x2A25: "Serial Number",
    0x2A26: "Firmware Revision",
    0x2A29: "Manufacturer Name",
}

BLUETOOTH_BASE_SUFFIX = "-0000-1000-8000-00805f9b34fb"

# What a captured value has to look like before we call it a candidate secret.
_PRINTABLE = re.compile(rb"[\x20-\x7e]{4,}")


class BtsnoopError(Exception):
    """The file is not a btsnoop capture we can read."""


@dataclass
class Record:
    """One raw btsnoop record, before any HCI interpretation."""

    index: int
    timestamp_us: int
    sent: bool
    data: bytes

    @property
    def direction(self) -> str:
        return "phone->cam" if self.sent else "cam->phone"


@dataclass
class AttPacket:
    """One reassembled ATT PDU."""

    index: int
    timestamp_us: int
    sent: bool
    connection: int
    opcode: int
    payload: bytes

    @property
    def name(self) -> str:
        return ATT_OPCODES.get(self.opcode, f"Unknown 0x{self.opcode:02x}")

    @property
    def direction(self) -> str:
        return "phone->cam" if self.sent else "cam->phone"

    @property
    def handle(self) -> int | None:
        """The attribute handle, for the opcodes that lead with one."""
        leads_with_handle = {0x0A, 0x0C, 0x12, 0x52, 0x16, 0x1B, 0x1D, 0xD2}
        if self.opcode in leads_with_handle and len(self.payload) >= 2:
            return struct.unpack_from("<H", self.payload)[0]
        return None

    @property
    def value(self) -> bytes:
        """The value bytes, with any leading handle stripped off."""
        if self.opcode in {0x0A, 0x0C}:
            return b""
        if self.handle is not None:
            offset = 4 if self.opcode == 0x16 else 2
            return self.payload[offset:]
        if self.opcode in {0x0B, 0x0D}:
            return self.payload
        return b""


@dataclass
class Capture:
    """A parsed capture: the ATT traffic plus what we learned about the handles."""

    packets: list[AttPacket] = field(default_factory=list)
    handle_uuids: dict[int, str] = field(default_factory=dict)
    records: int = 0

    @property
    def first_timestamp_us(self) -> int:
        return self.packets[0].timestamp_us if self.packets else 0

    def uuid_for(self, handle: int | None) -> str:
        if handle is None:
            return ""
        return self.handle_uuids.get(handle, "")


def format_uuid(raw: bytes) -> str:
    """Render a UUID from its little-endian on-the-wire form."""
    if len(raw) == 2:
        value = struct.unpack("<H", raw)[0]
        name = KNOWN_UUIDS.get(value)
        return f"0x{value:04x} {name}" if name else f"0x{value:04x}"
    if len(raw) == 16:
        b = raw[::-1]
        text = (
            f"{b[0:4].hex()}-{b[4:6].hex()}-{b[6:8].hex()}-{b[8:10].hex()}-{b[10:16].hex()}"
        )
        # A 128-bit UUID on the Bluetooth base is really a short one dressed up.
        if text.endswith(BLUETOOTH_BASE_SUFFIX):
            short = int(text[4:8], 16)
            name = KNOWN_UUIDS.get(short)
            return f"0x{short:04x} {name}" if name else f"0x{short:04x}"
        return text
    return raw.hex()


def _open_capture(path: Path) -> bytes:
    """Return the capture bytes, reaching into a bugreport zip when handed one."""
    if zipfile.is_zipfile(path):
        with zipfile.ZipFile(path) as archive:
            candidates = [n for n in archive.namelist() if "btsnoop" in n.lower()]
            if not candidates:
                raise BtsnoopError(f"no btsnoop log inside {path}")
            # A bugreport carries the live log and rotated older ones; take the live one.
            candidates.sort(key=lambda n: ("last" in n.lower(), n))
            return archive.read(candidates[0])
    return path.read_bytes()


def read_records(path: Path) -> Iterator[Record]:
    """Yield every record in the capture, without interpreting the HCI payload."""
    blob = _open_capture(path)
    if not blob.startswith(BTSNOOP_MAGIC):
        raise BtsnoopError(f"{path} does not start with the btsnoop magic")

    version, datalink = struct.unpack_from(">II", blob, len(BTSNOOP_MAGIC))
    if version != 1:
        raise BtsnoopError(f"unsupported btsnoop version {version}")
    if datalink not in (DATALINK_HCI_UNENCAP, DATALINK_HCI_UART):
        raise BtsnoopError(f"unsupported datalink type {datalink}")

    offset = len(BTSNOOP_MAGIC) + 8
    index = 0
    while offset + 24 <= len(blob):
        _orig_len, incl_len, flags, _drops, ts = struct.unpack_from(">IIIIq", blob, offset)
        offset += 24
        data = blob[offset : offset + incl_len]
        if len(data) < incl_len:
            break  # truncated tail, stop rather than emit a partial record
        offset += incl_len
        index += 1

        if datalink == DATALINK_HCI_UART:
            if not data:
                continue
            h4_type, data = data[0], data[1:]
        else:
            # Unencapsulated: bit 1 of flags says command/event, and direction the rest.
            h4_type = H4_EVENT if flags & 0x02 else H4_ACL

        yield Record(
            index=index,
            timestamp_us=ts,
            sent=not (flags & 0x01),
            data=bytes([h4_type]) + data,
        )


def _learn_from_response(capture: Capture, packet: AttPacket, pending_type: int | None) -> None:
    """Record handle-to-UUID mappings from a discovery response."""
    payload = packet.payload
    if packet.opcode == 0x05 and payload:  # Find Information Response
        fmt = payload[0]
        size = 4 if fmt == 0x01 else 18
        for pos in range(1, len(payload) - size + 1, size):
            handle = struct.unpack_from("<H", payload, pos)[0]
            capture.handle_uuids[handle] = format_uuid(payload[pos + 2 : pos + size])
    elif packet.opcode == 0x09 and payload:  # Read By Type Response
        item_len = payload[0]
        if pending_type == 0x2803 and item_len in (7, 21):
            for pos in range(1, len(payload) - item_len + 1, item_len):
                value_handle = struct.unpack_from("<H", payload, pos + 3)[0]
                capture.handle_uuids[value_handle] = format_uuid(
                    payload[pos + 5 : pos + item_len]
                )
    elif packet.opcode == 0x11 and payload:  # Read By Group Type Response
        item_len = payload[0]
        if item_len in (6, 20):
            for pos in range(1, len(payload) - item_len + 1, item_len):
                start = struct.unpack_from("<H", payload, pos)[0]
                capture.handle_uuids[start] = format_uuid(payload[pos + 4 : pos + item_len])


def parse(path: Path) -> Capture:
    """Parse a capture into its ATT packets, reassembling fragmented L2CAP."""
    capture = Capture()
    # One partial L2CAP buffer per (connection handle, direction).
    partial: dict[tuple[int, bool], bytearray] = {}
    pending_type: int | None = None

    for record in read_records(path):
        capture.records += 1
        if record.data[0] != H4_ACL or len(record.data) < 5:
            continue

        handle_flags, _length = struct.unpack_from("<HH", record.data, 1)
        connection = handle_flags & 0x0FFF
        pb_flag = (handle_flags >> 12) & 0x03
        fragment = record.data[5:]
        key = (connection, record.sent)

        if pb_flag == 0x01:  # continuation of an earlier fragment
            buffer = partial.get(key)
            if buffer is None:
                continue  # capture started mid-PDU; nothing to attach this to
            buffer.extend(fragment)
        else:
            buffer = bytearray(fragment)
            partial[key] = buffer

        if len(buffer) < 4:
            continue
        l2cap_len, cid = struct.unpack_from("<HH", buffer)
        if len(buffer) < l2cap_len + 4:
            continue  # more fragments to come

        pdu = bytes(buffer[4 : 4 + l2cap_len])
        del partial[key]

        if cid != L2CAP_CID_ATT or not pdu:
            continue

        packet = AttPacket(
            index=record.index,
            timestamp_us=record.timestamp_us,
            sent=record.sent,
            connection=connection,
            opcode=pdu[0],
            payload=pdu[1:],
        )
        capture.packets.append(packet)

        # Remember what a Read By Type Request asked for, to read its response.
        if packet.opcode == 0x08 and len(packet.payload) >= 6:
            pending_type = struct.unpack_from("<H", packet.payload, 4)[0]
        else:
            _learn_from_response(capture, packet, pending_type)

    return capture


def printable_strings(data: bytes, minimum: int = 4) -> list[str]:
    """Pull ASCII runs out of a value — this is how an SSID announces itself."""
    runs = (m.group() for m in _PRINTABLE.finditer(data))
    return [run.decode("ascii") for run in runs if len(run) >= minimum]


def format_packet(
    capture: Capture, packet: AttPacket, *, redact: bool = False, relative: bool = True
) -> str:
    """Render one packet as a single line."""
    if relative and capture.first_timestamp_us:
        stamp = f"{(packet.timestamp_us - capture.first_timestamp_us) / 1e6:9.3f}"
    else:
        stamp = f"{packet.timestamp_us / 1e6:9.3f}"

    parts = [stamp, packet.direction, packet.name]

    handle = packet.handle
    if handle is not None:
        uuid = capture.uuid_for(handle)
        parts.append(f"handle 0x{handle:04x}" + (f" [{uuid}]" if uuid else ""))

    value = packet.value
    if value:
        if redact:
            parts.append(f"{len(value)} bytes <redacted>")
        else:
            parts.append(value.hex())
            text = printable_strings(value)
            if text:
                parts.append(f'"{" | ".join(text)}"')

    return "  ".join(parts)
