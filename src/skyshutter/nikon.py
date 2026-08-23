"""Nikon vendor layer on top of PTP/IP.

The opcodes below are Nikon's published-by-reverse-engineering vendor set as
used by ``libgphoto2``.  Which of them a Coolpix P1100 actually implements is
not documented anywhere; ``DeviceInfo.operations_supported`` is the ground
truth and every high level helper here checks it before firing.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from enum import IntEnum, IntFlag

from .ptp import DeviceInfo, OperationCode, PtpError, ResponseCode
from .ptpip import PtpIpConnection

log = logging.getLogger(__name__)

JPEG_SOI = b"\xff\xd8\xff"
JPEG_EOI = b"\xff\xd9"


class NikonOperation(IntEnum):
    """Nikon vendor operations (0x90xx / 0x92xx)."""

    GET_PROFILE_ALL_DATA = 0x9006
    SEND_PROFILE_DATA = 0x9007
    DELETE_PROFILE = 0x9008
    SET_PROFILE_DATA = 0x9009
    ADVANCED_TRANSFER = 0x9010
    GET_FILE_INFO_IN_BLOCK = 0x9011
    CAPTURE = 0x90C0
    AF_DRIVE = 0x90C1
    SET_CONTROL_MODE = 0x90C2
    DEL_IMAGE_SDRAM = 0x90C3
    GET_LARGE_THUMB = 0x90C4
    GET_EVENT = 0x90C7
    DEVICE_READY = 0x90C8
    GET_VENDOR_PROP_CODES = 0x90CA
    AF_CAPTURE_SDRAM = 0x90CB
    GET_PICT_CTRL_DATA = 0x90CC
    SET_PICT_CTRL_DATA = 0x90CD
    GET_DEVICE_PTPIP_INFO = 0x90E0
    GET_PREVIEW_IMG = 0x9200
    START_LIVE_VIEW = 0x9201
    END_LIVE_VIEW = 0x9202
    GET_LIVE_VIEW_IMG = 0x9203
    MF_DRIVE = 0x9204
    CHANGE_AF_AREA = 0x9205
    AF_DRIVE_CANCEL = 0x9206
    INITIATE_CAPTURE_REC_IN_MEDIA = 0x9207
    GET_VENDOR_STORAGE_IDS = 0x9209
    START_MOVIE_REC_IN_CARD = 0x920A
    END_MOVIE_REC = 0x920B
    TERMINATE_CAPTURE = 0x920C
    #: Zoom, the way the compact cameras do it: two parameters, wide and tele,
    #: and only ever one of them non-zero. The mirrorless bodies use 0x9464.
    ZOOM_CONTROL = 0x9016
    POWER_ZOOM_BY_FOCAL_LENGTH = 0x941E
    #: The newer event poll. Where both exist the vendor app prefers this one;
    #: this camera offers only this one, not 0x90C7.
    GET_EVENT_EX = 0x941C
    START_AUTO_TRANSFER = 0x9520
    GET_AUTO_TRANSFER_LIST = 0x9521
    #: Fetch part of an object at a chosen size -- 8 megapixels instead of the
    #: full frame, for a quick look after a shot.
    GET_SPECIFIC_SIZE_PARTIAL_OBJECT = 0x9522


class NikonEvent(IntEnum):
    OBJECT_ADDED = 0x4002
    STORE_REMOVED = 0x4005
    DEVICE_PROP_CHANGED = 0x4006
    STORE_FULL = 0x400A
    CAPTURE_COMPLETE = 0x400D
    NIKON_OBJECT_ADDED_IN_SDRAM = 0xC101
    NIKON_CAPTURE_COMPLETE_RECINSDRAM = 0xC102
    NIKON_PREVIEW_IMAGE_ADDED = 0xC104
    RECORDING_INTERRUPTED = 0xC105
    MOVIE_RECORD_COMPLETE = 0xC108
    START_MOVIE_RECORD = 0xC10A


class NikonProperty(IntEnum):
    """Vendor properties, named from the vendor app (23.08.2026).

    Only the ones this camera actually reports are listed; ``d303``, ``d406``
    and ``d407`` are hers too but appear nowhere in the app.
    """

    STILL_FOCUS_METERING_MODE = 0xD05D
    LENS_SORT = 0xD0E1
    LENS_FOCAL_MIN = 0xD0E3
    LENS_FOCAL_MAX = 0xD0E4
    SHUTTER_SPEED = 0xD100
    LIVE_VIEW_STATUS = 0xD1A2
    #: Why live view refuses to start. -1 means "no reason, go ahead".
    LIVE_VIEW_PROHIBIT = 0xD1A4
    REMAINING_CAPTURE = 0xD1F1


class LiveViewProhibit(IntFlag):
    """Why the camera will not start live view -- property 0xD1A4.

    A bitmask, not a code: several reasons can hold at once. Zero means go
    ahead. Bit 24 is the one that stopped us over USB, and the vendor app
    ignores bit 31 entirely.
    """

    SEQUENCE_ERROR = 1 << 2
    MINIMUM_APERTURE_WARNING = 1 << 5
    BATTERY_SHORTAGE = 1 << 8
    TTL_ERROR = 1 << 9
    CPU_LENS_NOT_MOUNTED = 1 << 11
    IMAGE_IN_SDRAM = 1 << 12
    NO_CARD_RELEASE_DISABLED = 1 << 14
    DURING_SHOOTING_COMMAND = 1 << 15
    TEMPERATURE_RISE = 1 << 17
    CARD_PROTECTED = 1 << 18
    CARD_ERROR = 1 << 19
    CARD_UNFORMATTED = 1 << 20
    SHUTTER_SPEED_IS_TIME_SHOOTING = 1 << 21
    DURING_MIRROR_UP = 1 << 22
    POWER_OFF = 1 << 23
    #: "Lens is retracting" -- what the camera answers whenever USB is plugged in.
    LENS_RETRACTED = 1 << 24
    INCOMPATIBLE_EXPOSURE_MODE = 1 << 31


#: The live view header is a fixed 384 bytes; the JPEG starts right after it.
LIVE_VIEW_HEADER_LENGTH = 0x180


@dataclass(frozen=True)
class LiveViewFrame:
    """One live view frame: the picture plus what the camera says about it.

    The header is big-endian -- unlike the PTP framing around it, which is
    little-endian. Getting that backwards yields plausible-looking nonsense
    rather than an error.
    """

    jpeg: bytes
    width: int
    height: int
    whole_width: int
    whole_height: int
    #: Visible cut-out of the sensor: width, height, centre x, centre y.
    display_area: tuple[int, int, int, int]
    #: Autofocus frame, same four numbers.
    focus_area: tuple[int, int, int, int]
    #: Orientation in the camera's own units -- roll, pitch, yaw.
    roll: int
    pitch: int
    yaw: int
    rotation: int

    @property
    def zoom(self) -> float:
        """How far the visible area is zoomed into the sensor.

        Derived, not transmitted: the header carries no zoom factor. Falls
        back to 1.0 when the camera reports nothing useful.
        """
        if not self.display_area[0] or not self.whole_width:
            return 1.0
        return self.whole_width / self.display_area[0]


def parse_live_view(payload: bytes) -> LiveViewFrame | None:
    """Read a live view frame, header and all.

    The length field at offset 4 is only trusted as a sanity check: on cameras
    that support auto transfer the vendor app ignores it and takes the rest of
    the buffer instead, and this camera is one of those.
    """
    if len(payload) <= LIVE_VIEW_HEADER_LENGTH:
        return None
    head = payload[:LIVE_VIEW_HEADER_LENGTH]
    jpeg = extract_jpeg(payload[LIVE_VIEW_HEADER_LENGTH:])
    if jpeg is None:
        return None

    def s16(offset: int) -> int:
        return int.from_bytes(head[offset : offset + 2], "big", signed=True)

    def s32(offset: int) -> int:
        return int.from_bytes(head[offset : offset + 4], "big", signed=True)

    return LiveViewFrame(
        jpeg=jpeg,
        width=s16(0x08),
        height=s16(0x0A),
        whole_width=s16(0x0C),
        whole_height=s16(0x0E),
        display_area=(s16(0x10), s16(0x12), s16(0x14), s16(0x16)),
        focus_area=(s16(0x18), s16(0x1A), s16(0x1C), s16(0x1E)),
        roll=s32(0x34),
        pitch=s32(0x38),
        yaw=s32(0x3C),
        rotation=head[0x25],
    )


def extract_jpeg(payload: bytes) -> bytes | None:
    """Carve the JPEG out of a Nikon live view payload.

    Kept deliberately forgiving. The header is 384 bytes on this camera, but
    8 and 128 have been reported elsewhere, and a client that hunts for the
    markers works on all of them.
    """
    start = payload.find(JPEG_SOI)
    if start < 0:
        return None
    end = payload.rfind(JPEG_EOI)
    if end < 0 or end <= start:
        return None
    return payload[start : end + len(JPEG_EOI)]


class NikonCamera:
    """High level control of a Nikon camera reachable over PTP/IP."""

    def __init__(self, connection: PtpIpConnection) -> None:
        self.connection = connection
        self.device_info: DeviceInfo | None = None

    # -- lifecycle ---------------------------------------------------------

    @classmethod
    @contextmanager
    def open(cls, host: str, **kwargs: object) -> Iterator[NikonCamera]:
        connection = PtpIpConnection(host, **kwargs)  # type: ignore[arg-type]
        connection.connect()
        camera = cls(connection)
        try:
            connection.open_session()
            camera.refresh_device_info()
            yield camera
        finally:
            connection.close_session()
            connection.close()

    def refresh_device_info(self) -> DeviceInfo:
        result = self.connection.transaction(OperationCode.GET_DEVICE_INFO)
        self.device_info = DeviceInfo.parse(result.data)
        return self.device_info

    def supports(self, opcode: int) -> bool:
        return self.device_info is not None and self.device_info.supports(opcode)

    def _require(self, opcode: int, what: str) -> None:
        if self.device_info is not None and not self.device_info.supports(opcode):
            raise PtpError(ResponseCode.OPERATION_NOT_SUPPORTED, opcode)
        log.debug("using %s for %s", NikonOperation(opcode).name, what)

    # -- status ------------------------------------------------------------

    def wait_until_ready(self, timeout: float = 5.0, interval: float = 0.1) -> bool:
        """Poll ``NIKON_DeviceReady`` until the camera stops reporting busy."""
        if not self.supports(NikonOperation.DEVICE_READY):
            return True
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            result = self.connection.transaction(
                NikonOperation.DEVICE_READY, raise_on_error=False
            )
            if result.response_code != ResponseCode.DEVICE_BUSY:
                return result.ok
            time.sleep(interval)
        return False

    def get_events(self) -> list[tuple[int, int]]:
        """Poll the camera's event queue; returns ``(event code, parameter)``.

        There are two of these operations with different payloads, and a camera
        may offer either. The vendor app prefers the newer one where both
        exist -- and this camera has *only* the newer one, so asking for
        ``GetEvent`` alone would silently return nothing forever.

        Events are polled, not pushed: the event channel carries the handshake
        and the keepalive, but the vendor app never reads an event packet off
        it. Waiting for one would wait forever.
        """
        if self.supports(NikonOperation.GET_EVENT_EX):
            return self._parse_events_ex(
                self.connection.transaction(NikonOperation.GET_EVENT_EX).data
            )
        if self.supports(NikonOperation.GET_EVENT):
            return self._parse_events(self.connection.transaction(NikonOperation.GET_EVENT).data)
        return []

    @staticmethod
    def _parse_events(data: bytes) -> list[tuple[int, int]]:
        """0x90C7: uint16 count, then per event a code and one parameter."""
        if len(data) < 2:
            return []
        count = int.from_bytes(data[:2], "little")
        events: list[tuple[int, int]] = []
        offset = 2
        for _ in range(count):
            if offset + 6 > len(data):
                break
            code = int.from_bytes(data[offset : offset + 2], "little")
            param = int.from_bytes(data[offset + 2 : offset + 6], "little")
            events.append((code, param))
            offset += 6
        return events

    @staticmethod
    def _parse_events_ex(data: bytes) -> list[tuple[int, int]]:
        """0x941C: uint32 count, then per event a code, a count and n parameters.

        Only the first parameter is handed back -- it is the one that carries
        the object handle, the storage id or the property code. The rest are
        kept out of the way until something needs them.
        """
        if len(data) < 4:
            return []
        count = int.from_bytes(data[:4], "little")
        events: list[tuple[int, int]] = []
        offset = 4
        for _ in range(count):
            if offset + 4 > len(data):
                break
            code = int.from_bytes(data[offset : offset + 2], "little")
            params = int.from_bytes(data[offset + 2 : offset + 4], "little")
            offset += 4
            first = 0
            if params and offset + 4 <= len(data):
                first = int.from_bytes(data[offset : offset + 4], "little")
            offset += 4 * params
            events.append((code, first))
        return events

    # -- shooting ----------------------------------------------------------

    def autofocus(self) -> None:
        self._require(NikonOperation.AF_DRIVE, "autofocus")
        self.connection.transaction(NikonOperation.AF_DRIVE)
        self.wait_until_ready()

    def capture(self) -> None:
        """Release the shutter, preferring the most capable opcode available."""
        if self.supports(NikonOperation.INITIATE_CAPTURE_REC_IN_MEDIA):
            # (0xFFFFFFFF, 0) = "current AF area", "record to card"
            self.connection.transaction(
                NikonOperation.INITIATE_CAPTURE_REC_IN_MEDIA, (0xFFFFFFFF, 0x00000000)
            )
        elif self.supports(NikonOperation.CAPTURE):
            self.connection.transaction(NikonOperation.CAPTURE)
        else:
            self.connection.transaction(OperationCode.INITIATE_CAPTURE, (0, 0))
        self.wait_until_ready()

    # -- live view ---------------------------------------------------------

    def start_live_view(self) -> None:
        self._require(NikonOperation.START_LIVE_VIEW, "live view")
        self.connection.transaction(NikonOperation.START_LIVE_VIEW)
        self.wait_until_ready()

    def end_live_view(self) -> None:
        self.connection.transaction(NikonOperation.END_LIVE_VIEW, raise_on_error=False)

    def get_live_view_frame(self) -> bytes | None:
        """One live view JPEG, or ``None`` while the camera has nothing yet."""
        result = self.connection.transaction(
            NikonOperation.GET_LIVE_VIEW_IMG, raise_on_error=False
        )
        if not result.ok:
            if result.response_code == ResponseCode.DEVICE_BUSY:
                return None
            raise PtpError(result.response_code, NikonOperation.GET_LIVE_VIEW_IMG)
        return extract_jpeg(result.data)

    @contextmanager
    def live_view(self) -> Iterator[NikonCamera]:
        self.start_live_view()
        try:
            yield self
        finally:
            self.end_live_view()

    def stream_live_view(self, fps: float = 15.0) -> Iterator[bytes]:
        """Yield live view JPEG frames until the caller stops consuming."""
        interval = 1.0 / fps if fps > 0 else 0.0
        with self.live_view():
            while True:
                started = time.monotonic()
                frame = self.get_live_view_frame()
                if frame:
                    yield frame
                delay = interval - (time.monotonic() - started)
                if delay > 0:
                    time.sleep(delay)
