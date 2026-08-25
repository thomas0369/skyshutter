from __future__ import annotations

import pytest

from skyshutter.ptp import (
    DeviceInfo,
    OperationCode,
    PtpError,
    ResponseCode,
    Unpacker,
    code_name,
    pack_string,
)


def test_pack_string_roundtrip() -> None:
    packed = pack_string("Z 6_1234")
    assert packed[0] == 9  # 8 characters plus the terminator
    assert Unpacker(packed).string() == "Z 6_1234"


def test_pack_empty_string() -> None:
    assert pack_string("") == b"\x00"
    assert Unpacker(b"\x00").string() == ""


def test_unpacker_reads_little_endian() -> None:
    u = Unpacker(bytes.fromhex("010200030000000400000000000000"))
    assert u.uint8() == 1
    assert u.uint16() == 2
    assert u.uint32() == 3
    assert u.uint64() == 4
    assert u.remaining == 0


def test_unpacker_rejects_truncated_data() -> None:
    with pytest.raises(ValueError, match="truncated"):
        Unpacker(b"\x01").uint32()


def test_unpacker_array() -> None:
    data = b"\x03\x00\x00\x00" + b"\x01\x10\x02\x10\x03\x10"
    assert Unpacker(data).array() == [0x1001, 0x1002, 0x1003]


def test_unpacker_array_prevents_memory_exhaustion() -> None:
    # array count is 2^30, but remaining data is 0 bytes
    data = b"\x00\x00\x00\x40"
    with pytest.raises(ValueError, match="exceeds remaining data"):
        Unpacker(data).array()


def test_device_info_roundtrip() -> None:
    original = DeviceInfo(
        standard_version=100,
        vendor_extension_id=0x0000000A,
        vendor_extension_version=100,
        vendor_extension_desc="microsoft.com/DeviceServices:1.0;",
        operations_supported=[0x1001, 0x1002, 0x9207],
        events_supported=[0x4002],
        device_properties_supported=[0x5001],
        capture_formats=[0x3801],
        image_formats=[0x3801],
        manufacturer="Nikon Corporation",
        model="COOLPIX P1100",
        device_version="1.0",
        serial_number="0123456789abcdef",
    )
    parsed = DeviceInfo.parse(original.pack())
    assert parsed == original
    assert parsed.is_nikon
    assert parsed.supports(0x9207)
    assert not parsed.supports(0x9203)


def test_device_info_tolerates_missing_string_block() -> None:
    """Some firmware truncates the dataset; the numeric part must still parse."""
    full = DeviceInfo(operations_supported=[0x1001], model="X").pack()
    truncated = full[:-2]
    parsed = DeviceInfo.parse(truncated)
    assert parsed.operations_supported == [0x1001]


def test_code_name_falls_back_to_hex() -> None:
    assert code_name(ResponseCode.OK, ResponseCode) == "OK"
    assert code_name(0x9203, OperationCode) == "0x9203"


def test_ptp_error_message() -> None:
    error = PtpError(ResponseCode.DEVICE_BUSY, 0x9203)
    assert "DEVICE_BUSY" in str(error)
    assert "0x9203" in str(error)
    assert error.code == ResponseCode.DEVICE_BUSY
