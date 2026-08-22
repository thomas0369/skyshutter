"""The USB transport, pinned without a camera attached.

The framing is what this transport is; everything else it borrows. So the
tests drive a fake pair of bulk endpoints and check that what goes out and
what comes back matches the containers a real camera exchanges -- including
the one measured against the hardware on 23.08.2026.
"""

from __future__ import annotations

import struct

import pytest

from skyshutter.ptp import OperationCode, PtpError, ResponseCode
from skyshutter.ptpusb import (
    CONTAINER_HEADER,
    TYPE_COMMAND,
    TYPE_DATA,
    TYPE_RESPONSE,
    PtpUsbConnection,
    PtpUsbError,
    _container,
)


class FakeEndpoint:
    """Stands in for a bulk endpoint, handing back canned containers."""

    # pyusb's own spelling; a stand-in has to answer to the same name.
    wMaxPacketSize = 512  # noqa: N815

    def __init__(self, chunks: list[bytes] | None = None) -> None:
        self.chunks = chunks or []
        self.written: list[bytes] = []

    def write(self, payload, timeout=None) -> int:
        self.written.append(bytes(payload))
        return len(payload)

    def read(self, size, timeout=None):
        if not self.chunks:
            raise PtpUsbError("nothing left to read")
        return self.chunks.pop(0)


def connection(chunks: list[bytes]) -> PtpUsbConnection:
    conn = PtpUsbConnection(device=None)
    conn._in = FakeEndpoint(chunks)
    conn._out = FakeEndpoint()
    return conn


def response(code: int, transaction_id: int = 1, params: tuple[int, ...] = ()) -> bytes:
    return _container(
        TYPE_RESPONSE, code, transaction_id, b"".join(struct.pack("<I", p) for p in params)
    )


def test_container_header_is_twelve_bytes():
    raw = _container(TYPE_COMMAND, OperationCode.GET_DEVICE_INFO, 1)
    assert len(raw) == CONTAINER_HEADER
    length, kind, code, tid = struct.unpack("<IHHI", raw)
    assert (length, kind, code, tid) == (12, TYPE_COMMAND, 0x1001, 1)


def test_command_carries_its_parameters():
    conn = connection([response(ResponseCode.OK)])
    conn.transaction(OperationCode.OPEN_SESSION, (1,))
    sent = conn._out.written[0]
    assert len(sent) == CONTAINER_HEADER + 4
    assert struct.unpack_from("<I", sent, CONTAINER_HEADER)[0] == 1


def test_transaction_ids_advance():
    conn = connection([response(ResponseCode.OK, 1), response(ResponseCode.OK, 2)])
    conn.transaction(OperationCode.GET_DEVICE_INFO)
    conn.transaction(OperationCode.GET_DEVICE_INFO)
    first = struct.unpack_from("<I", conn._out.written[0], 8)[0]
    second = struct.unpack_from("<I", conn._out.written[1], 8)[0]
    assert (first, second) == (1, 2)


def test_data_phase_is_returned_with_the_response():
    payload = b"skyshutter"
    conn = connection(
        [
            _container(TYPE_DATA, OperationCode.GET_DEVICE_INFO, 1, payload),
            response(ResponseCode.OK),
        ]
    )
    result = conn.transaction(OperationCode.GET_DEVICE_INFO)
    assert result.data == payload
    assert result.ok


def test_a_long_data_phase_is_reassembled():
    """A container larger than one packet arrives in pieces."""
    payload = bytes(range(256)) * 4  # 1024 bytes, more than one 512-byte read
    full = _container(TYPE_DATA, OperationCode.GET_DEVICE_INFO, 1, payload)
    conn = connection([full[:512], full[512:], response(ResponseCode.OK)])
    result = conn.transaction(OperationCode.GET_DEVICE_INFO)
    assert result.data == payload


def test_data_out_is_sent_as_its_own_container():
    conn = connection([response(ResponseCode.OK)])
    conn.transaction(OperationCode.SET_DEVICE_PROP_VALUE, (0x5008,), data=b"\x00\x10")
    assert len(conn._out.written) == 2
    _, kind, _, _ = struct.unpack("<IHHI", conn._out.written[1][:CONTAINER_HEADER])
    assert kind == TYPE_DATA


def test_an_error_response_raises():
    conn = connection([response(ResponseCode.OPERATION_NOT_SUPPORTED)])
    with pytest.raises(PtpError):
        conn.transaction(0x9204)  # MfDrive, which this camera does not have


def test_an_error_response_can_be_tolerated():
    conn = connection([response(ResponseCode.OPERATION_NOT_SUPPORTED)])
    result = conn.transaction(0x9204, raise_on_error=False)
    assert not result.ok
    assert result.response_code == ResponseCode.OPERATION_NOT_SUPPORTED


def test_response_parameters_are_unpacked():
    conn = connection([response(ResponseCode.OK, params=(7, 9))])
    result = conn.transaction(OperationCode.GET_DEVICE_INFO)
    assert result.parameters == (7, 9)


def test_writing_without_endpoints_fails_clearly():
    conn = PtpUsbConnection(device=None)
    with pytest.raises(PtpUsbError, match="not connected"):
        conn.transaction(OperationCode.GET_DEVICE_INFO)


def test_an_already_open_session_is_not_an_error():
    """Measured behaviour: reconnecting to a live session must not throw."""
    conn = connection([response(ResponseCode.SESSION_ALREADY_OPEN)])
    conn.open_session()  # must not raise
