from __future__ import annotations

import socket
import struct

import pytest

from skyshutter.ptpip import (
    HEADER_SIZE,
    DataPhase,
    Packet,
    PacketType,
    PtpIpError,
    decode_operation_response,
    decode_utf16,
    encode_operation_request,
    encode_utf16,
    read_packet,
    send_packet,
)


def test_packet_encoding_includes_header_in_length() -> None:
    packet = Packet(PacketType.PING, b"\x01\x02")
    encoded = packet.encode()
    length, ptype = struct.unpack("<II", encoded[:HEADER_SIZE])
    assert length == len(encoded) == HEADER_SIZE + 2
    assert ptype == PacketType.PING


def test_packet_type_name_for_unknown_type() -> None:
    assert Packet(0x99).type_name == "UNKNOWN(0x00000099)"
    assert Packet(PacketType.EVENT).type_name == "EVENT"


def test_operation_request_layout() -> None:
    packet = encode_operation_request(0x1002, 7, (1,))
    phase, opcode, transaction_id = struct.unpack("<IHI", packet.payload[:10])
    assert phase == DataPhase.NONE_OR_IN
    assert opcode == 0x1002
    assert transaction_id == 7
    assert struct.unpack("<I", packet.payload[10:14])[0] == 1


def test_operation_request_rejects_too_many_parameters() -> None:
    with pytest.raises(ValueError, match="at most 5"):
        encode_operation_request(0x1001, 1, (1, 2, 3, 4, 5, 6))


def test_operation_response_decoding() -> None:
    payload = struct.pack("<HI", 0x2001, 42) + struct.pack("<II", 0xAA, 0xBB)
    code, transaction_id, params = decode_operation_response(
        Packet(PacketType.OPERATION_RESPONSE, payload)
    )
    assert (code, transaction_id, params) == (0x2001, 42, (0xAA, 0xBB))


def test_utf16_helpers_roundtrip() -> None:
    assert decode_utf16(encode_utf16("skyshutter")) == "skyshutter"
    # trailing bytes after the terminator are ignored, as cameras pad the field
    assert decode_utf16(encode_utf16("P1100") + b"\xff\xff") == "P1100"


def test_read_packet_reassembles_fragmented_frames() -> None:
    left, right = socket.socketpair()
    try:
        encoded = Packet(PacketType.DATA, bytes(range(200))).encode()
        for offset in range(0, len(encoded), 7):
            left.sendall(encoded[offset : offset + 7])
        packet = read_packet(right)
        assert packet.type == PacketType.DATA
        assert packet.payload == bytes(range(200))
    finally:
        left.close()
        right.close()


def test_read_packet_detects_closed_connection() -> None:
    left, right = socket.socketpair()
    left.close()
    try:
        with pytest.raises(PtpIpError, match="connection closed"):
            read_packet(right)
    finally:
        right.close()


def test_read_packet_rejects_absurd_length() -> None:
    left, right = socket.socketpair()
    try:
        left.sendall(struct.pack("<II", 0xFFFFFFF0, PacketType.DATA))
        with pytest.raises(PtpIpError, match="refusing packet"):
            read_packet(right)
    finally:
        left.close()
        right.close()


def test_send_and_read_packet_roundtrip() -> None:
    left, right = socket.socketpair()
    try:
        send_packet(left, Packet(PacketType.INIT_EVENT_ACK))
        packet = read_packet(right)
        assert packet.type == PacketType.INIT_EVENT_ACK
        assert packet.payload == b""
    finally:
        left.close()
        right.close()
