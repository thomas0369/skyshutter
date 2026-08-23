from __future__ import annotations

from skyshutter.nikon import (
    LIVE_VIEW_HEADER_LENGTH,
    LiveViewProhibit,
    NikonCamera,
    NikonOperation,
    NikonProperty,
    extract_jpeg,
    parse_live_view,
)


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


def test_opcodes_measured_on_the_camera_are_named() -> None:
    """The six that came back unnamed from the hardware, now resolved.

    Measured 23.08.2026 in operations_supported; the names come from the
    vendor app. A typo here turns a working command into "not supported".
    """
    assert NikonOperation.ZOOM_CONTROL == 0x9016
    assert NikonOperation.GET_EVENT_EX == 0x941C
    assert NikonOperation.POWER_ZOOM_BY_FOCAL_LENGTH == 0x941E
    assert NikonOperation.START_AUTO_TRANSFER == 0x9520
    assert NikonOperation.GET_AUTO_TRANSFER_LIST == 0x9521
    assert NikonOperation.GET_SPECIFIC_SIZE_PARTIAL_OBJECT == 0x9522


def test_this_camera_has_the_new_event_poll_and_not_the_old_one() -> None:
    """Measured: 0x941C is in the list, 0x90C7 is not.

    Asking only for GetEvent would return an empty list forever instead of
    failing loudly, which is the kind of bug that costs an evening.
    """
    measured = {
        0x9016, 0x90C1, 0x90C2, 0x90C4, 0x90C8, 0x9201, 0x9202, 0x9203,
        0x9205, 0x9207, 0x941C, 0x941E, 0x9520, 0x9521, 0x9522,
    }
    assert NikonOperation.GET_EVENT_EX in measured
    assert NikonOperation.GET_EVENT not in measured


def test_the_two_event_payloads_are_parsed_differently() -> None:
    """0x90C7 counts in 16 bits with one parameter; 0x941C in 32 with n."""
    old = (1).to_bytes(2, "little") + (0x4002).to_bytes(2, "little") + (7).to_bytes(4, "little")
    assert NikonCamera._parse_events(old) == [(0x4002, 7)]

    new = (
        (1).to_bytes(4, "little")
        + (0x4002).to_bytes(2, "little")
        + (2).to_bytes(2, "little")
        + (7).to_bytes(4, "little")
        + (9).to_bytes(4, "little")
    )
    assert NikonCamera._parse_events_ex(new) == [(0x4002, 7)]


def test_event_parsers_survive_a_truncated_payload() -> None:
    assert NikonCamera._parse_events(b"") == []
    assert NikonCamera._parse_events_ex(b"") == []
    assert NikonCamera._parse_events_ex((5).to_bytes(4, "little")) == []


def test_an_event_without_parameters_still_parses() -> None:
    payload = (1).to_bytes(4, "little") + (0xC702).to_bytes(2, "little") + (0).to_bytes(2, "little")
    assert NikonCamera._parse_events_ex(payload) == [(0xC702, 0)]


def test_live_view_prohibit_property_is_pinned() -> None:
    """The property that told us "Lens is retracting" over USB."""
    assert NikonProperty.LIVE_VIEW_PROHIBIT == 0xD1A4
    assert NikonProperty.LIVE_VIEW_STATUS == 0xD1A2
    assert NikonProperty.SHUTTER_SPEED == 0xD100


def _live_view_payload(**fields: int) -> bytes:
    """Build a frame the way the camera does: 384-byte big-endian header."""
    head = bytearray(LIVE_VIEW_HEADER_LENGTH)
    for offset, value in fields.items():
        pos = int(offset[1:], 16)
        head[pos : pos + 2] = int(value).to_bytes(2, "big", signed=True)
    return bytes(head) + b"\xff\xd8\xff" + b"frame" + b"\xff\xd9"


def test_live_view_header_is_big_endian() -> None:
    """The header runs the other way round than the PTP framing around it.

    640 as big-endian is 0x0280; read as little-endian it would be 32770.
    """
    frame = parse_live_view(_live_view_payload(x08=640, x0A=480))
    assert frame is not None
    assert (frame.width, frame.height) == (640, 480)


def test_live_view_frame_carries_the_jpeg_after_the_header() -> None:
    frame = parse_live_view(_live_view_payload(x08=640))
    assert frame is not None
    assert frame.jpeg == b"\xff\xd8\xff" + b"frame" + b"\xff\xd9"


def test_live_view_zoom_is_derived_from_the_visible_area() -> None:
    """No zoom factor is transmitted; it follows from sensor vs. cut-out."""
    frame = parse_live_view(_live_view_payload(x0C=1000, x10=250))
    assert frame is not None
    assert frame.zoom == 4.0


def test_live_view_zoom_falls_back_when_the_camera_says_nothing() -> None:
    frame = parse_live_view(_live_view_payload(x08=640))
    assert frame is not None
    assert frame.zoom == 1.0


def test_a_payload_shorter_than_the_header_is_no_frame() -> None:
    assert parse_live_view(b"") is None
    assert parse_live_view(bytes(LIVE_VIEW_HEADER_LENGTH)) is None


def test_a_header_without_a_jpeg_is_no_frame() -> None:
    assert parse_live_view(bytes(LIVE_VIEW_HEADER_LENGTH) + b"not a picture") is None


def test_the_lens_retracted_bit_is_the_one_usb_hit() -> None:
    """Measured over USB: the camera refused live view with exactly this reason."""
    assert LiveViewProhibit.LENS_RETRACTED == 1 << 24
    reason = LiveViewProhibit(1 << 24)
    assert LiveViewProhibit.LENS_RETRACTED in reason
    assert LiveViewProhibit.BATTERY_SHORTAGE not in reason


def test_several_prohibit_reasons_can_hold_at_once() -> None:
    reason = LiveViewProhibit(LiveViewProhibit.POWER_OFF | LiveViewProhibit.CARD_ERROR)
    assert LiveViewProhibit.POWER_OFF in reason
    assert LiveViewProhibit.CARD_ERROR in reason
    assert LiveViewProhibit.LENS_RETRACTED not in reason
