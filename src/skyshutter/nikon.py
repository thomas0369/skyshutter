"""Nikon vendor layer on top of PTP/IP.

The opcodes below are Nikon's published-by-reverse-engineering vendor set as
used by ``libgphoto2``.  Which of them a Coolpix P1100 actually implements is
not documented anywhere; ``DeviceInfo.operations_supported`` is the ground
truth and every high level helper here checks it before firing.
"""

from __future__ import annotations

import logging
import struct
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from enum import IntEnum, IntFlag

from .ptp import (
    DeviceInfo,
    OperationCode,
    PropertyDesc,
    PtpError,
    ResponseCode,
    StorageInfo,
    Unpacker,
    code_name,
)
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
    #: libgphoto2 calls this SetControlMode; the vendor app calls it
    #: ChangeCameraMode and also uses it around starting and stopping live
    #: view. Setting it to 1 over USB was refused by this camera.
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
        log.debug("using %s for %s", code_name(opcode, NikonOperation), what)

    # -- status ------------------------------------------------------------

    def wait_until_ready(self, timeout: float = 5.0, interval: float = 0.1) -> bool:
        """Poll ``NIKON_DeviceReady`` until the camera stops reporting busy."""
        if not self.supports(NikonOperation.DEVICE_READY):
            return True
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            result = self.connection.transaction(NikonOperation.DEVICE_READY, raise_on_error=False)
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

    # -- properties --------------------------------------------------------

    def get_property(self, code: int) -> bytes:
        """Raw value of a device property."""
        return self.connection.transaction(OperationCode.GET_DEVICE_PROP_VALUE, (code,)).data

    def get_property_u32(self, code: int) -> int:
        raw = self.get_property(code)
        return int.from_bytes(raw[:4], "little") if len(raw) >= 4 else 0

    def set_property(self, code: int, value: bytes) -> None:
        """Set raw value of a device property."""
        self.connection.transaction(OperationCode.SET_DEVICE_PROP_VALUE, (code,), data=value)

    def set_property_u32(self, code: int, value: int) -> None:
        """Set uint32 value of a device property."""
        self.set_property(code, struct.pack("<I", value))

    @staticmethod
    def _parse_code_list(data: bytes) -> list[int]:
        """uint16 property codes from a vendor list operation.

        The wire format of ``GetVendorPropCodes`` is not documented. Two shapes
        are plausible -- a bare run of uint16 values, or a PTP array with a
        uint32 count prefix. The array form is tried first because it is what
        the rest of the protocol uses; the bare run is the fallback.
        """
        if len(data) >= 4:
            count = int.from_bytes(data[:4], "little")
            if count * 2 == len(data) - 4:
                return [int.from_bytes(data[4 + i * 2 : 6 + i * 2], "little") for i in range(count)]
        return [int.from_bytes(data[i * 2 : i * 2 + 2], "little") for i in range(len(data) // 2)]

    def vendor_property_codes(self) -> list[int]:
        """The vendor device-property codes this camera offers (0x90CA)."""
        result = self.connection.transaction(NikonOperation.GET_VENDOR_PROP_CODES)
        return self._parse_code_list(result.data)

    def property_desc(self, code: int) -> PropertyDesc:
        """The descriptor (type, access, value range) of one device property."""
        result = self.connection.transaction(OperationCode.GET_DEVICE_PROP_DESC, (code,))
        return PropertyDesc.parse(result.data)

    def properties(self) -> dict[int, PropertyDesc]:
        """Every known device property with its descriptor.

        Combines the standard ``device_properties_supported`` list with the
        vendor codes from 0x90CA, then asks the camera for each descriptor. A
        property the camera refuses to describe is skipped, not fatal -- the
        goal is a map of what is there, not an all-or-nothing dump.
        """
        codes = set(self.device_info.device_properties_supported) if self.device_info else set()
        try:
            codes.update(self.vendor_property_codes())
        except PtpError as exc:
            log.debug("vendor property codes unavailable: %s", exc)
        out: dict[int, PropertyDesc] = {}
        for code in sorted(codes):
            try:
                out[code] = self.property_desc(code)
            except PtpError as exc:
                log.debug("no descriptor for 0x%04X: %s", code, exc)
        return out

    def storage_ids(self) -> list[int]:
        """The storage media this camera exposes."""
        result = self.connection.transaction(OperationCode.GET_STORAGE_IDS)
        u = Unpacker(result.data)
        return u.array("uint32")

    def storage_info(self, storage_id: int) -> StorageInfo:
        """Capacity and free space of one storage medium."""
        result = self.connection.transaction(OperationCode.GET_STORAGE_INFO, (storage_id,))
        return StorageInfo.parse(result.data)

    def live_view_prohibit(self) -> LiveViewProhibit:
        """Why live view would refuse right now; falsy when nothing is in the way.

        Worth asking *before* starting, not after failing: over USB this is
        what reports the retracted lens, and the answer names the reason
        instead of leaving a bare error code.
        """
        return LiveViewProhibit(self.get_property_u32(NikonProperty.LIVE_VIEW_PROHIBIT))

    def live_view_running(self) -> bool:
        return bool(self.get_property_u32(NikonProperty.LIVE_VIEW_STATUS))

    # -- shooting ----------------------------------------------------------

    def autofocus(self) -> None:
        self._require(NikonOperation.AF_DRIVE, "autofocus")
        self.connection.transaction(NikonOperation.AF_DRIVE)
        self.wait_until_ready()

    def zoom(self, steps: int) -> None:
        """Drive the optical zoom: positive towards tele, negative towards wide.

        Two parameters, and exactly one of them carries the amount -- that is
        how the compact bodies do it. The mirrorless ones use a different
        opcode this camera does not have.
        """
        self._require(NikonOperation.ZOOM_CONTROL, "zoom")
        wide, tele = (0, steps) if steps >= 0 else (abs(steps), 0)
        self.connection.transaction(NikonOperation.ZOOM_CONTROL, (wide, tele))
        self.wait_until_ready()

    def capture(self, autofocus: bool = False, target: int = 0) -> None:
        """Release the shutter.

        ``target`` picks where the picture lands: 0 card, 1 the camera's own
        memory, 2 both. The vendor app always says 0; 1 skips the card
        entirely, which is untested here but is what the camera offers.
        """
        if self.supports(NikonOperation.INITIATE_CAPTURE_REC_IN_MEDIA):
            # First parameter is a signed -1 for a plain release, -2 to focus
            # first; it travels as an unsigned word.
            release = 0xFFFFFFFE if autofocus else 0xFFFFFFFF
            self.connection.transaction(
                NikonOperation.INITIATE_CAPTURE_REC_IN_MEDIA, (release, target)
            )
        elif self.supports(NikonOperation.CAPTURE):
            self.connection.transaction(NikonOperation.CAPTURE)
        else:
            self.connection.transaction(OperationCode.INITIATE_CAPTURE, (0, 0))
        # The camera reports "busy" until the picture is written; that, not an
        # event, is what the vendor app waits for.
        self.wait_until_ready(timeout=30.0)

    # -- images ------------------------------------------------------------

    def download(self, handle: int, size: int, chunk: int = 1 << 20) -> bytes:
        """Fetch an image in pieces.

        The vendor app never uses plain ``GetObject`` -- everything comes
        through ``GetPartialObject`` in one-megabyte blocks, with no size
        threshold. That also means a transfer can be resumed rather than
        restarted, which matters over a camera's own access point.
        """
        self._require(OperationCode.GET_PARTIAL_OBJECT, "download")
        received = bytearray()
        while len(received) < size:
            want = min(chunk, size - len(received))
            result = self.connection.transaction(
                OperationCode.GET_PARTIAL_OBJECT, (handle, len(received), want)
            )
            if not result.data:
                break
            received += result.data
        return bytes(received)

    # -- live view ---------------------------------------------------------

    def start_live_view(self, attempts: int = 10, pause: float = 0.5) -> None:
        """Start live view, checking first why it might refuse.

        The vendor app reads the prohibit condition before it tries, and
        retries up to ten times half a second apart while the camera says
        busy. Both are worth copying: the check turns a bare error into a
        named reason, and the camera does report busy on the first attempt.
        """
        self._require(NikonOperation.START_LIVE_VIEW, "live view")

        reason = self.live_view_prohibit()
        if reason:
            raise PtpError(ResponseCode.DEVICE_BUSY, NikonOperation.START_LIVE_VIEW)

        if self.live_view_running():
            log.debug("live view is already running, not starting it again")
            return

        for attempt in range(1, attempts + 1):
            result = self.connection.transaction(
                NikonOperation.START_LIVE_VIEW, raise_on_error=False
            )
            if result.ok:
                self.wait_until_ready()
                return
            if result.response_code != ResponseCode.DEVICE_BUSY:
                raise PtpError(result.response_code, NikonOperation.START_LIVE_VIEW)
            log.debug("live view busy, attempt %d/%d", attempt, attempts)
            time.sleep(pause)
        raise PtpError(ResponseCode.DEVICE_BUSY, NikonOperation.START_LIVE_VIEW)

    def end_live_view(self) -> None:
        self.connection.transaction(NikonOperation.END_LIVE_VIEW, raise_on_error=False)

    def get_live_view_frame(self) -> bytes | None:
        """One live view JPEG, or ``None`` while the camera has nothing yet."""
        frame = self.get_live_view()
        return frame.jpeg if frame else None

    def get_live_view(self) -> LiveViewFrame | None:
        """One live view frame with everything the camera reports about it.

        Beyond the picture that is the visible cut-out of the sensor, the
        autofocus frame and the orientation sensor -- worth having when the
        camera sits on a tripod pointing at the sky.
        """
        result = self.connection.transaction(NikonOperation.GET_LIVE_VIEW_IMG, raise_on_error=False)
        if not result.ok:
            if result.response_code == ResponseCode.DEVICE_BUSY:
                return None
            raise PtpError(result.response_code, NikonOperation.GET_LIVE_VIEW_IMG)
        frame = parse_live_view(result.data)
        if frame is not None:
            return frame
        # Shorter header than this camera uses; keep the picture anyway.
        jpeg = extract_jpeg(result.data)
        if jpeg is None:
            return None
        return LiveViewFrame(jpeg, 0, 0, 0, 0, (0, 0, 0, 0), (0, 0, 0, 0), 0, 0, 0, 0)

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
