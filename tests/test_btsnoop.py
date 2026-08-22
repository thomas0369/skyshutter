"""Tests for the btsnoop reader, built on synthetic captures.

Every capture here is assembled byte by byte from the format description, not
recorded from a phone. That keeps the tests honest about what the parser is
promised to handle, and keeps real credentials out of the repository.
"""

from __future__ import annotations

import struct
import zipfile

import pytest

from skyshutter import btsnoop
from skyshutter.btsnoop import BtsnoopError, format_uuid, parse, printable_strings

# --- capture builders -------------------------------------------------------


def build_capture(records: list[tuple[bool, bytes]], *, datalink: int = 1002) -> bytes:
    """Assemble a btsnoop file from (sent, h4_packet) pairs."""
    out = bytearray(btsnoop.BTSNOOP_MAGIC)
    out += struct.pack(">II", 1, datalink)
    for index, (sent, payload) in enumerate(records):
        flags = 0 if sent else 1
        timestamp = btsnoop.BTSNOOP_EPOCH_DELTA_US + index * 1_000_000
        out += struct.pack(">IIIIq", len(payload), len(payload), flags, 0, timestamp)
        out += payload
    return bytes(out)


def acl(pdu: bytes, *, connection: int = 0x0040, first: bool = True) -> bytes:
    """Wrap an already-framed L2CAP fragment in an ACL packet."""
    pb_flag = 0x00 if first else 0x01
    handle_flags = connection | (pb_flag << 12)
    return bytes([btsnoop.H4_ACL]) + struct.pack("<HH", handle_flags, len(pdu)) + pdu


def l2cap(att_pdu: bytes, *, cid: int = btsnoop.L2CAP_CID_ATT) -> bytes:
    return struct.pack("<HH", len(att_pdu), cid) + att_pdu


def write_command(handle: int, value: bytes) -> bytes:
    return struct.pack("<BH", 0x52, handle) + value


# --- header handling --------------------------------------------------------


def test_rejects_a_file_that_is_not_a_capture(tmp_path):
    path = tmp_path / "nonsense.log"
    path.write_bytes(b"this is not a capture")
    with pytest.raises(BtsnoopError, match="magic"):
        parse(path)


def test_rejects_an_unsupported_datalink(tmp_path):
    path = tmp_path / "weird.log"
    path.write_bytes(build_capture([], datalink=99))
    with pytest.raises(BtsnoopError, match="datalink"):
        parse(path)


def test_reads_a_bugreport_zip(tmp_path):
    inner = build_capture([(True, acl(l2cap(write_command(0x0010, b"hi"))))])
    path = tmp_path / "bugreport.zip"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("FS/data/log/bt/btsnoop_hci.log", inner)
    capture = parse(path)
    assert len(capture.packets) == 1


def test_zip_without_a_capture_is_an_error(tmp_path):
    path = tmp_path / "bugreport.zip"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("FS/data/log/main.log", b"nothing here")
    with pytest.raises(BtsnoopError, match="no btsnoop log"):
        parse(path)


# --- ATT decoding -----------------------------------------------------------


def test_decodes_a_write_command(tmp_path):
    path = tmp_path / "c.log"
    path.write_bytes(build_capture([(True, acl(l2cap(write_command(0x0021, b"\x01\x02"))))]))

    capture = parse(path)
    assert capture.records == 1
    packet = capture.packets[0]
    assert packet.name == "Write Command"
    assert packet.handle == 0x0021
    assert packet.value == b"\x01\x02"
    assert packet.direction == "phone->cam"


def test_notification_from_the_camera_reads_as_inbound(tmp_path):
    pdu = struct.pack("<BH", 0x1B, 0x0033) + b"\xaa\xbb"
    path = tmp_path / "c.log"
    path.write_bytes(build_capture([(False, acl(l2cap(pdu)))]))

    packet = parse(path).packets[0]
    assert packet.name == "Handle Value Notification"
    assert packet.direction == "cam->phone"
    assert packet.value == b"\xaa\xbb"


def test_read_request_carries_a_handle_but_no_value(tmp_path):
    path = tmp_path / "c.log"
    path.write_bytes(build_capture([(True, acl(l2cap(struct.pack("<BH", 0x0A, 0x0009))))]))

    packet = parse(path).packets[0]
    assert packet.handle == 0x0009
    assert packet.value == b""


def test_non_att_channels_are_ignored(tmp_path):
    smp = l2cap(b"\x01\x02\x03", cid=btsnoop.L2CAP_CID_SMP)
    path = tmp_path / "c.log"
    path.write_bytes(build_capture([(True, acl(smp))]))

    capture = parse(path)
    assert capture.records == 1
    assert capture.packets == []


def test_reassembles_a_fragmented_pdu(tmp_path):
    # A 40-byte write split across two ACL packets, as a small MTU forces.
    value = bytes(range(40))
    pdu = l2cap(write_command(0x0021, value))
    path = tmp_path / "c.log"
    path.write_bytes(
        build_capture(
            [
                (True, acl(pdu[:20], first=True)),
                (True, acl(pdu[20:], first=False)),
            ]
        )
    )

    capture = parse(path)
    assert len(capture.packets) == 1
    assert capture.packets[0].value == value


def test_a_continuation_without_a_start_is_dropped(tmp_path):
    """Captures that begin mid-transfer must not produce a bogus packet."""
    path = tmp_path / "c.log"
    path.write_bytes(build_capture([(True, acl(b"\x01\x02\x03", first=False))]))

    capture = parse(path)
    assert capture.packets == []


def test_two_connections_do_not_mix_their_fragments(tmp_path):
    left = l2cap(write_command(0x0011, b"AAAA"))
    right = l2cap(write_command(0x0022, b"BBBB"))
    path = tmp_path / "c.log"
    path.write_bytes(
        build_capture(
            [
                (True, acl(left[:5], connection=0x0040, first=True)),
                (True, acl(right[:5], connection=0x0041, first=True)),
                (True, acl(left[5:], connection=0x0040, first=False)),
                (True, acl(right[5:], connection=0x0041, first=False)),
            ]
        )
    )

    capture = parse(path)
    values = {p.handle: p.value for p in capture.packets}
    assert values == {0x0011: b"AAAA", 0x0022: b"BBBB"}


# --- handle discovery -------------------------------------------------------


def test_learns_handles_from_a_find_information_response(tmp_path):
    body = b"\x01" + struct.pack("<HH", 0x0003, 0x2A00) + struct.pack("<HH", 0x0005, 0x2A19)
    pdu = bytes([0x05]) + body
    path = tmp_path / "c.log"
    path.write_bytes(build_capture([(False, acl(l2cap(pdu)))]))

    capture = parse(path)
    assert capture.uuid_for(0x0003) == "0x2a00 Device Name"
    assert capture.uuid_for(0x0005) == "0x2a19 Battery Level"


def test_learns_a_vendor_uuid_from_a_characteristic_declaration(tmp_path):
    vendor = bytes.fromhex("fbb39d9b8000008010000000cdab0000")
    request = struct.pack("<BHHH", 0x08, 0x0001, 0xFFFF, 0x2803)
    item = struct.pack("<HBH", 0x0010, 0x0A, 0x0011) + vendor
    response = bytes([0x09, 21]) + item
    path = tmp_path / "c.log"
    path.write_bytes(
        build_capture([(True, acl(l2cap(request))), (False, acl(l2cap(response)))])
    )

    capture = parse(path)
    # The value handle, not the declaration handle, is what later writes address.
    assert capture.uuid_for(0x0011) == format_uuid(vendor)
    assert capture.uuid_for(0x0010) == ""


def test_a_read_by_type_response_for_another_type_is_not_mistaken_for_a_characteristic(
    tmp_path,
):
    request = struct.pack("<BHHH", 0x08, 0x0001, 0xFFFF, 0x2A00)
    response = bytes([0x09, 7]) + struct.pack("<HBH", 0x0010, 0x0A, 0x0011) + b"\x00\x2a"
    path = tmp_path / "c.log"
    path.write_bytes(
        build_capture([(True, acl(l2cap(request))), (False, acl(l2cap(response)))])
    )

    assert parse(path).handle_uuids == {}


def test_learns_services_from_a_group_type_response(tmp_path):
    item = struct.pack("<HHH", 0x0001, 0x0007, 0x1800)
    pdu = bytes([0x11, 6]) + item
    path = tmp_path / "c.log"
    path.write_bytes(build_capture([(False, acl(l2cap(pdu)))]))

    assert parse(path).uuid_for(0x0001) == "0x1800 Generic Access"


# --- UUID rendering ---------------------------------------------------------


def test_short_uuid_is_named_when_known():
    assert format_uuid(struct.pack("<H", 0x2A00)) == "0x2a00 Device Name"


def test_unknown_short_uuid_is_rendered_bare():
    assert format_uuid(struct.pack("<H", 0xABCD)) == "0xabcd"


def test_long_uuid_on_the_bluetooth_base_collapses_to_its_short_form():
    base = bytes.fromhex("fb349b5f80000080001000000f180000")
    assert format_uuid(base) == "0x180f Battery Service"


def test_vendor_uuid_is_rendered_in_full():
    raw = bytes.fromhex("efcdab89674523011032547698badcfe")
    assert format_uuid(raw) == "fedcba98-7654-3210-0123-456789abcdef"


# --- secrets ----------------------------------------------------------------


def test_finds_a_readable_string_in_a_value():
    assert "Nikon_WU2" in printable_strings(b"\x01\x00Nikon_WU2\x00\xff")


def test_ignores_runs_that_are_too_short():
    assert printable_strings(b"\x00ab\x00") == []


def test_redaction_hides_the_bytes_but_keeps_the_shape(tmp_path):
    secret = b"passphrase123"
    path = tmp_path / "c.log"
    path.write_bytes(build_capture([(True, acl(l2cap(write_command(0x0021, secret))))]))

    capture = parse(path)
    line = btsnoop.format_packet(capture, capture.packets[0], redact=True)

    assert "passphrase123" not in line
    assert secret.hex() not in line
    assert "13 bytes <redacted>" in line
    assert "handle 0x0021" in line


def test_the_default_rendering_shows_the_value(tmp_path):
    path = tmp_path / "c.log"
    path.write_bytes(build_capture([(True, acl(l2cap(write_command(0x0021, b"SSID_here"))))]))

    capture = parse(path)
    line = btsnoop.format_packet(capture, capture.packets[0])
    assert "SSID_here" in line
    assert "phone->cam" in line


def test_timestamps_are_relative_to_the_first_packet(tmp_path):
    pdu = l2cap(write_command(0x0021, b"x"))
    path = tmp_path / "c.log"
    path.write_bytes(build_capture([(True, acl(pdu)), (True, acl(pdu))]))

    capture = parse(path)
    first = btsnoop.format_packet(capture, capture.packets[0])
    second = btsnoop.format_packet(capture, capture.packets[1])
    assert first.strip().startswith("0.000")
    assert second.strip().startswith("1.000")


# --- robustness -------------------------------------------------------------


def test_a_truncated_tail_stops_the_read_instead_of_raising(tmp_path):
    good = build_capture([(True, acl(l2cap(write_command(0x0021, b"ok"))))])
    path = tmp_path / "c.log"
    path.write_bytes(good + struct.pack(">IIIIq", 99, 99, 0, 0, 0) + b"\x02\x03")

    capture = parse(path)
    assert len(capture.packets) == 1
