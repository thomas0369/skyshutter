from __future__ import annotations

from skyshutter.nikon import NikonOperation, extract_jpeg


def test_extract_jpeg_skips_the_vendor_header() -> None:
    frame = b"\xff\xd8\xff" + b"payload" + b"\xff\xd9"
    assert extract_jpeg(bytes(384) + frame) == frame
    assert extract_jpeg(bytes(8) + frame) == frame


def test_extract_jpeg_ignores_trailing_padding() -> None:
    frame = b"\xff\xd8\xff" + b"payload" + b"\xff\xd9"
    assert extract_jpeg(bytes(128) + frame + bytes(16)) == frame


def test_extract_jpeg_returns_none_without_markers() -> None:
    assert extract_jpeg(b"") is None
    assert extract_jpeg(bytes(100)) is None
    assert extract_jpeg(b"\xff\xd8\xff no end marker") is None


def test_live_view_opcodes_match_the_documented_vendor_set() -> None:
    # Guards against a typo silently turning into "camera says not supported".
    assert NikonOperation.START_LIVE_VIEW == 0x9201
    assert NikonOperation.END_LIVE_VIEW == 0x9202
    assert NikonOperation.GET_LIVE_VIEW_IMG == 0x9203
    assert NikonOperation.INITIATE_CAPTURE_REC_IN_MEDIA == 0x9207
    assert NikonOperation.DEVICE_READY == 0x90C8
