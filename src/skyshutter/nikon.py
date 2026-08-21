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
from enum import IntEnum

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


class NikonEvent(IntEnum):
    OBJECT_ADDED = 0x4002
    CAPTURE_COMPLETE = 0x400D
    NIKON_OBJECT_ADDED_IN_SDRAM = 0xC101
    NIKON_CAPTURE_COMPLETE_RECINSDRAM = 0xC102
    NIKON_PREVIEW_IMAGE_ADDED = 0xC104


def extract_jpeg(payload: bytes) -> bytes | None:
    """Carve the JPEG out of a Nikon live view payload.

    Nikon prefixes the frame with a model dependent header (8, 128, 384 bytes
    have all been observed), so the marker is located instead of assumed.
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
        """Drain ``NIKON_GetEvent``; returns ``(event code, parameter)`` pairs."""
        if not self.supports(NikonOperation.GET_EVENT):
            return []
        data = self.connection.transaction(NikonOperation.GET_EVENT).data
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
