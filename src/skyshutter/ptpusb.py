"""PTP over USB, the second transport.

PTP/IP and PTP over USB carry the same operations; only the framing differs.
Where PTP/IP wraps everything in typed TCP packets, USB uses three bulk
transfers with a 12-byte container header:

    +0  uint32  length, including these 12 bytes
    +4  uint16  container type: 1 command, 2 data, 3 response, 4 event
    +6  uint16  operation or response code
    +8  uint32  transaction id
    +12         parameters (command, response) or payload (data)

Because :class:`PtpUsbConnection` offers the same ``transaction`` method as
:class:`~skyshutter.ptpip.PtpIpConnection`, everything built on top of it --
``NikonCamera``, the MJPEG server, the CLI -- works over a cable without
changes.

Measured 23.08.2026 on the real camera: this reaches it and reads its device
info. Live view over USB does not work, but that is the camera's own doing --
it retracts the lens as soon as USB is connected and then refuses to start.
"""

from __future__ import annotations

import struct
from collections.abc import Iterator
from contextlib import contextmanager

from .ptp import DeviceInfo, OperationCode, PtpError, ResponseCode
from .ptpip import Transaction

#: The camera reports itself under this vendor; the product id differs per model.
NIKON_VENDOR_ID = 0x04B0

#: USB still-image class, as every PTP camera declares it.
IMAGE_CLASS = 6

CONTAINER_HEADER = 12

TYPE_COMMAND = 1
TYPE_DATA = 2
TYPE_RESPONSE = 3
TYPE_EVENT = 4


class PtpUsbError(RuntimeError):
    """Transport level failure (no device, framing, timeout)."""


def _container(kind: int, code: int, transaction_id: int, payload: bytes = b"") -> bytes:
    return (
        struct.pack("<IHHI", CONTAINER_HEADER + len(payload), kind, code, transaction_id) + payload
    )


class PtpUsbConnection:
    """One PTP session over a USB cable."""

    def __init__(self, device, timeout: int = 5000) -> None:
        self.device = device
        self.timeout = timeout
        self._transaction_id = 0
        self.device_info: DeviceInfo | None = None
        self._in = self._out = None

    # -- setup ---------------------------------------------------------------

    @classmethod
    @contextmanager
    def open(
        cls, vendor: int = NIKON_VENDOR_ID, product: int | None = None, **kwargs: object
    ) -> Iterator[PtpUsbConnection]:
        """Find the camera, claim it, and close it again afterwards."""
        try:
            import usb.core
            import usb.util
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise PtpUsbError("pyusb is missing: pip install pyusb") from exc

        criteria = {"idVendor": vendor}
        if product is not None:
            criteria["idProduct"] = product
        device = usb.core.find(**criteria)
        if device is None:
            raise PtpUsbError(
                f"no USB device {vendor:04x}:{product:04x}"
                if product
                else f"no USB device from vendor {vendor:04x}"
            )

        connection = cls(device, **kwargs)  # type: ignore[arg-type]
        connection.claim()
        try:
            yield connection
        finally:
            connection.close()

    def claim(self) -> None:
        """Pick the still-image interface and remember its bulk endpoints."""
        import usb.util

        configuration = self.device.get_active_configuration()
        interface = None
        for candidate in configuration:
            if candidate.bInterfaceClass == IMAGE_CLASS:
                interface = candidate
                break
        if interface is None:
            raise PtpUsbError("the device has no still-image interface")

        # Linux binds its own driver to cameras; without detaching it every
        # transfer fails with "Resource busy".
        if self.device.is_kernel_driver_active(interface.bInterfaceNumber):
            self.device.detach_kernel_driver(interface.bInterfaceNumber)

        for endpoint in interface:
            direction = usb.util.endpoint_direction(endpoint.bEndpointAddress)
            kind = usb.util.endpoint_type(endpoint.bmAttributes)
            if kind != usb.util.ENDPOINT_TYPE_BULK:
                continue
            if direction == usb.util.ENDPOINT_IN:
                self._in = endpoint
            else:
                self._out = endpoint
        if self._in is None or self._out is None:
            raise PtpUsbError("the still-image interface has no bulk endpoints")

    def close(self) -> None:
        try:
            import usb.util

            usb.util.dispose_resources(self.device)
        except Exception:  # pragma: no cover - teardown must not raise
            pass

    # -- framing -------------------------------------------------------------

    def next_transaction_id(self) -> int:
        self._transaction_id = (self._transaction_id + 1) & 0xFFFFFFFF
        return self._transaction_id

    def _read_container(self) -> tuple[int, int, int, bytes]:
        """Read one container, following it across as many packets as it takes."""
        first = bytes(self._in.read(self._in.wMaxPacketSize, self.timeout))
        if len(first) < CONTAINER_HEADER:
            raise PtpUsbError(f"short container: {len(first)} bytes")
        length, kind, code, transaction_id = struct.unpack("<IHHI", first[:CONTAINER_HEADER])
        payload = bytearray(first[CONTAINER_HEADER:length])
        while len(payload) + CONTAINER_HEADER < length:
            chunk = bytes(self._in.read(self._in.wMaxPacketSize, self.timeout))
            if not chunk:
                raise PtpUsbError("the device stopped mid-container")
            payload.extend(chunk)
        return kind, code, transaction_id, bytes(payload[: length - CONTAINER_HEADER])

    def transaction(
        self,
        opcode: int,
        params: tuple[int, ...] = (),
        data: bytes | None = None,
        raise_on_error: bool = True,
    ) -> Transaction:
        """Run one PTP operation and return its response (and any data-in)."""
        if self._out is None:
            raise PtpUsbError("not connected")

        transaction_id = self.next_transaction_id()
        self._out.write(
            _container(
                TYPE_COMMAND, opcode, transaction_id, b"".join(struct.pack("<I", p) for p in params)
            ),
            self.timeout,
        )
        if data is not None:
            self._out.write(_container(TYPE_DATA, opcode, transaction_id, data), self.timeout)

        received = b""
        while True:
            kind, code, _tid, payload = self._read_container()
            if kind == TYPE_DATA:
                received = payload
                continue
            if kind == TYPE_RESPONSE:
                parameters = tuple(
                    struct.unpack_from("<I", payload, offset)[0]
                    for offset in range(0, len(payload) - 3, 4)
                )
                result = Transaction(code, parameters, received)
                break
            if kind == TYPE_EVENT:
                continue
            raise PtpUsbError(f"unexpected container type {kind}")

        if raise_on_error and not result.ok:
            raise PtpError(result.response_code, opcode)
        return result

    # -- the one operation every session starts with -------------------------

    def get_device_info(self) -> DeviceInfo:
        result = self.transaction(OperationCode.GET_DEVICE_INFO)
        self.device_info = DeviceInfo.parse(result.data)
        return self.device_info

    def open_session(self, session_id: int = 1) -> None:
        result = self.transaction(OperationCode.OPEN_SESSION, (session_id,), raise_on_error=False)
        # A session that is already open is not a problem worth stopping for.
        if not result.ok and result.response_code != ResponseCode.SESSION_ALREADY_OPEN:
            raise PtpError(result.response_code, OperationCode.OPEN_SESSION)

    def close_session(self) -> None:
        self.transaction(OperationCode.CLOSE_SESSION, raise_on_error=False)
