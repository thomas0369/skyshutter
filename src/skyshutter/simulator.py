"""A fake Nikon PTP/IP responder.

The camera is not always on the desk, and its WiFi cannot coexist with a
normal network connection.  The simulator answers the same handshake and the
subset of operations skyshutter uses, so the client can be developed and
tested without hardware::

    python -m skyshutter.simulator --port 15740
    skyshutter --host 127.0.0.1 info

It is a development aid, not a model of the real camera: the operation list is
what a Nikon *typically* advertises, not what a P1100 was measured to support.
"""

from __future__ import annotations

import argparse
import logging
import socket
import socketserver
import struct
import uuid

from .nikon import DriveMode, ExposureProgram, NikonOperation, NikonProperty, StandardProperty
from .ptp import (
    AccessCapability,
    DataType,
    DeviceInfo,
    FormFlag,
    OperationCode,
    PropertyDesc,
    ResponseCode,
    StorageInfo,
    VendorExtension,
)
from .ptpip import (
    DEFAULT_PORT,
    Packet,
    PacketType,
    decode_utf16,
    encode_utf16,
    read_packet,
    send_packet,
)

log = logging.getLogger(__name__)

SIMULATED_OPERATIONS = [
    OperationCode.GET_DEVICE_INFO,
    OperationCode.OPEN_SESSION,
    OperationCode.CLOSE_SESSION,
    OperationCode.GET_STORAGE_IDS,
    OperationCode.GET_STORAGE_INFO,
    OperationCode.GET_OBJECT_HANDLES,
    OperationCode.GET_OBJECT_INFO,
    OperationCode.GET_OBJECT,
    OperationCode.GET_THUMB,
    OperationCode.INITIATE_CAPTURE,
    OperationCode.GET_DEVICE_PROP_DESC,
    OperationCode.GET_DEVICE_PROP_VALUE,
    OperationCode.SET_DEVICE_PROP_VALUE,
    OperationCode.GET_PARTIAL_OBJECT,
    NikonOperation.GET_SPECIFIC_SIZE_PARTIAL_OBJECT,
    NikonOperation.CAPTURE,
    NikonOperation.AF_DRIVE,
    # Measured 23.08.2026: the real camera offers only the newer event poll,
    # not 0x90C7. The simulator says the same, so a client that asks for the
    # old one here fails here instead of on the bench.
    NikonOperation.GET_EVENT_EX,
    NikonOperation.DEVICE_READY,
    NikonOperation.START_LIVE_VIEW,
    NikonOperation.END_LIVE_VIEW,
    NikonOperation.GET_LIVE_VIEW_IMG,
    NikonOperation.INITIATE_CAPTURE_REC_IN_MEDIA,
    NikonOperation.ZOOM_CONTROL,
    NikonOperation.GET_VENDOR_PROP_CODES,
]

SIMULATOR_GUID = uuid.UUID("5c9a7e00-0000-4000-8000-000000000001")

#: What the simulated sensor and its visible cut-out measure.
SIM_JPEG_SIZE = (640, 480)
SIM_WHOLE_SIZE = (1000, 750)


def _live_view_header(jpeg_length: int) -> bytes:
    """The 384-byte frame header, big-endian, as the vendor app reads it."""
    head = bytearray(0x180)
    head[0x04:0x08] = jpeg_length.to_bytes(4, "big")
    head[0x08:0x0A] = SIM_JPEG_SIZE[0].to_bytes(2, "big")
    head[0x0A:0x0C] = SIM_JPEG_SIZE[1].to_bytes(2, "big")
    head[0x0C:0x0E] = SIM_WHOLE_SIZE[0].to_bytes(2, "big")
    head[0x0E:0x10] = SIM_WHOLE_SIZE[1].to_bytes(2, "big")
    # Visible area: the full sensor, so the derived zoom comes out as 1.0.
    head[0x10:0x12] = SIM_WHOLE_SIZE[0].to_bytes(2, "big")
    head[0x12:0x14] = SIM_WHOLE_SIZE[1].to_bytes(2, "big")
    return bytes(head)


def _placeholder_jpeg() -> bytes:
    """A JPEG frame if Pillow is around, otherwise a marker-framed stand-in."""
    return _sized_jpeg((640, 480), b"skyshutter simulated frame")


def _preview_jpeg() -> bytes:
    """Preview stand-in: stands for the measured 1440x1080 JPEG (0x9522).

    Kept at 320x240 so the invariant "preview smaller than the stored
    frame" holds in the Pillow-less text mode too.
    """
    return _sized_jpeg((320, 240), b"simulated preview")


def _sized_jpeg(size: tuple[int, int], marker_text: bytes) -> bytes:
    try:
        import io

        from PIL import Image, ImageDraw
    except ImportError:
        return b"\xff\xd8\xff" + marker_text + b"\xff\xd9"
    image = Image.new("RGB", size, (24, 24, 32))
    ImageDraw.Draw(image).text((20, 20), marker_text.decode(), fill=(220, 220, 220))
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG")
    return buffer.getvalue()


def simulated_device_info() -> DeviceInfo:
    return DeviceInfo(
        standard_version=100,
        vendor_extension_id=VendorExtension.NIKON,
        vendor_extension_version=100,
        vendor_extension_desc="microsoft.com/DeviceServices:1.0;",
        functional_mode=0,
        operations_supported=[int(op) for op in SIMULATED_OPERATIONS],
        events_supported=[0x4002, 0x400D, 0xC101, 0xC102],
        device_properties_supported=[
            0x5001,
            0x5005,
            int(StandardProperty.F_NUMBER),
            int(StandardProperty.FOCAL_LENGTH),
            int(StandardProperty.FOCUS_MODE),
            int(StandardProperty.EXPOSURE_PROGRAM),
            int(StandardProperty.ISO),
            int(StandardProperty.EXPOSURE_BIAS),
            int(StandardProperty.STILL_CAPTURE_MODE),
            int(NikonProperty.SHUTTER_SPEED),
            int(NikonProperty.LIVE_VIEW_STATUS),
            int(NikonProperty.LIVE_VIEW_PROHIBIT),
            int(NikonProperty.REMAINING_CAPTURE),
            int(NikonProperty.LENS_FOCAL_MIN),
            int(NikonProperty.LENS_FOCAL_MAX),
        ],
        capture_formats=[0x3801],
        image_formats=[0x3801, 0x3000],
        manufacturer="Nikon Corporation",
        model="COOLPIX P1100 (simulated)",
        device_version="1.0",
        serial_number="0000000000000000",
    )


class _Handler(socketserver.BaseRequestHandler):
    server: SimulatorServer

    def handle(self) -> None:
        sock: socket.socket = self.request
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        sock.settimeout(5.0)
        try:
            while True:
                packet = read_packet(sock)
                self.dispatch(sock, packet)
        except Exception as exc:
            log.debug("connection closed: %s", exc)

    def dispatch(self, sock: socket.socket, packet: Packet) -> None:
        if packet.type == PacketType.INIT_COMMAND_REQUEST:
            client_guid = uuid.UUID(bytes=packet.payload[:16])
            client_name = decode_utf16(packet.payload[16:-4])
            log.info("client %s (%s) connected", client_name, client_guid)
            self.server.connection_number += 1
            payload = struct.pack("<I", self.server.connection_number)
            payload += self.server.guid.bytes + encode_utf16(self.server.name)
            payload += struct.pack("<I", 0x00010000)
            send_packet(sock, Packet(PacketType.INIT_COMMAND_ACK, payload))
        elif packet.type == PacketType.INIT_EVENT_REQUEST:
            send_packet(sock, Packet(PacketType.INIT_EVENT_ACK))
        elif packet.type == PacketType.OPERATION_REQUEST:
            self.handle_operation(sock, packet)
        elif packet.type == PacketType.PING:
            send_packet(sock, Packet(PacketType.PONG))
        else:
            log.warning("unhandled %s", packet.type_name)

    def handle_operation(self, sock: socket.socket, packet: Packet) -> None:
        data_phase, opcode, transaction_id = struct.unpack("<IHI", packet.payload[:10])
        # Parameters follow the ten header bytes, four bytes each. Property
        # reads need them -- without, every property looks like the same one.
        raw = packet.payload[10:]
        params = tuple(
            struct.unpack_from("<I", raw, offset)[0] for offset in range(0, len(raw) - 3, 4)
        )
        incoming_data = b""
        if data_phase == 2:  # DataPhase.OUT
            start = read_packet(sock)
            if start.type != PacketType.START_DATA:
                log.warning("expected START_DATA, got %s", start.type_name)
            end = read_packet(sock)
            if end.type != PacketType.END_DATA:
                log.warning("expected END_DATA, got %s", end.type_name)
            incoming_data = end.payload[4:]  # skip transaction_id
        code, data = self.server.operation(opcode, params, incoming_data)
        log.info("operation 0x%04X -> 0x%04X (%d bytes)", opcode, code, len(data))
        if data:
            send_packet(
                sock, Packet(PacketType.START_DATA, struct.pack("<IQ", transaction_id, len(data)))
            )
            send_packet(sock, Packet(PacketType.END_DATA, struct.pack("<I", transaction_id) + data))
        send_packet(
            sock, Packet(PacketType.OPERATION_RESPONSE, struct.pack("<HI", code, transaction_id))
        )


class SimulatorServer(socketserver.ThreadingTCPServer):
    """Serves the fake camera; one instance handles command and event links."""

    allow_reuse_address = True
    daemon_threads = True

    def __init__(self, host: str = "127.0.0.1", port: int = DEFAULT_PORT) -> None:
        super().__init__((host, port), _Handler)
        self.guid = SIMULATOR_GUID
        self.name = "COOLPIX P1100"
        self.connection_number = 0
        self.device_info = simulated_device_info()
        self.frame = _placeholder_jpeg()
        self.live_view_active = False
        self.captures = 0
        #: Captures land on the "card" as objects, oldest first, so the
        #: download path has something to walk -- like the real camera does.
        self.objects: dict[int, bytes] = {}
        self.filenames: dict[int, str] = {}
        self._next_handle = 0x10000001
        #: Device property values as raw bytes, in the wire format each
        #: property uses -- the shutter pair travels as eight bytes, the
        #: rest as uint32. Stored bytes-first so the client sees exactly
        #: what it sent.
        self.properties: dict[int, bytes] = {
            NikonProperty.LIVE_VIEW_STATUS: struct.pack("<I", 0),
            NikonProperty.LIVE_VIEW_PROHIBIT: struct.pack("<I", 0),
            # 1/60 s as the vendor form: numerator, denominator.
            NikonProperty.SHUTTER_SPEED: struct.pack(
                "<I", (1 << 16) | 60
            ),  # packed pair: 1/60 s, the measured desc default
            NikonProperty.REMAINING_CAPTURE: struct.pack("<I", 999),
            NikonProperty.LENS_FOCAL_MIN: struct.pack("<I", 24),
            NikonProperty.LENS_FOCAL_MAX: struct.pack("<I", 3000),
            StandardProperty.F_NUMBER: struct.pack("<H", 280),  # f/2.8, UINT16
            StandardProperty.FOCAL_LENGTH: struct.pack("<I", 24),
            StandardProperty.FOCUS_MODE: struct.pack("<H", 0x8010),  # AF-S, UINT16
            StandardProperty.EXPOSURE_PROGRAM: struct.pack("<H", int(ExposureProgram.PROGRAM_AUTO)),
            StandardProperty.ISO: struct.pack("<H", 100),  # 0 would be Auto
            StandardProperty.EXPOSURE_BIAS: struct.pack("<h", 0),  # INT16 millistops
            StandardProperty.STILL_CAPTURE_MODE: struct.pack("<H", int(DriveMode.SINGLE)),
        }

    def operation(
        self, opcode: int, params: tuple[int, ...] = (), incoming_data: bytes = b""
    ) -> tuple[int, bytes]:
        if opcode == OperationCode.GET_DEVICE_INFO:
            return ResponseCode.OK, self.device_info.pack()
        if opcode == OperationCode.GET_DEVICE_PROP_VALUE:
            code = params[0] if params else 0
            if code in self.properties:
                return ResponseCode.OK, self.properties[code]
            return ResponseCode.OPERATION_NOT_SUPPORTED, b""
        if opcode == OperationCode.SET_DEVICE_PROP_VALUE:
            code = params[0] if params else 0
            if code in self.properties and incoming_data:
                self.properties[code] = incoming_data
                return ResponseCode.OK, b""
            return ResponseCode.OPERATION_NOT_SUPPORTED, b""
        if opcode == OperationCode.GET_PARTIAL_OBJECT:
            # (handle, offset, length) -- hand back that slice of the object.
            handle, offset, length = (*params, 0, 0, 0)[:3]
            blob = self.objects.get(handle, self.frame)
            return ResponseCode.OK, blob[offset : offset + length]
        if opcode == OperationCode.GET_OBJECT_HANDLES:
            handles = list(self.objects)
            return ResponseCode.OK, struct.pack(f"<I{len(handles)}I", len(handles), *handles)
        if opcode == OperationCode.GET_OBJECT_INFO:
            handle = params[0] if params else 0
            blob = self.objects.get(handle)
            if blob is None:
                return ResponseCode.INVALID_OBJECT_HANDLE, b""
            return ResponseCode.OK, self._object_info(handle, blob)
        if opcode in (OperationCode.OPEN_SESSION, OperationCode.CLOSE_SESSION):
            return ResponseCode.OK, b""
        if opcode == NikonOperation.DEVICE_READY:
            return ResponseCode.OK, b""
        if opcode == NikonOperation.GET_EVENT_EX:
            # uint32 count, then per event a code, a parameter count, and the
            # parameters themselves.
            return ResponseCode.OK, struct.pack("<I", 0)
        if opcode == NikonOperation.START_LIVE_VIEW:
            self.live_view_active = True
            return ResponseCode.OK, b""
        if opcode == NikonOperation.END_LIVE_VIEW:
            self.live_view_active = False
            return ResponseCode.OK, b""
        if opcode == NikonOperation.GET_LIVE_VIEW_IMG:
            if not self.live_view_active:
                return ResponseCode.DEVICE_BUSY, b""
            return ResponseCode.OK, _live_view_header(len(self.frame)) + self.frame
        if opcode == NikonOperation.ZOOM_CONTROL:
            return ResponseCode.OK, b""
        if opcode == NikonOperation.GET_SPECIFIC_SIZE_PARTIAL_OBJECT:
            # Size-code matrix measured 26.08. at HW: 1 and 3 deliver the
            # same preview, 2 has no thumbnail, the rest are invalid.
            handle = params[0] if params else 0
            size_code = params[1] if len(params) > 1 else 0
            if handle not in self.objects:
                return ResponseCode.INVALID_OBJECT_HANDLE, b""
            if size_code in (1, 3):
                return ResponseCode.OK, _preview_jpeg()
            if size_code == 2:
                return ResponseCode.NO_THUMBNAIL_PRESENT, b""
            return ResponseCode.INVALID_PARAMETER, b""
        if opcode in (
            OperationCode.INITIATE_CAPTURE,
            NikonOperation.CAPTURE,
            NikonOperation.INITIATE_CAPTURE_REC_IN_MEDIA,
            NikonOperation.AF_DRIVE,
        ):
            if opcode is not NikonOperation.AF_DRIVE:
                handle = self._next_handle
                self._next_handle += 1
                self.objects[handle] = self.frame
                self.filenames[handle] = f"DSC_{0x2000 + len(self.objects):04d}.JPG"
            self.captures += 1
            return ResponseCode.OK, b""
        if opcode == NikonOperation.GET_VENDOR_PROP_CODES:
            # uint32 count, then the vendor property codes as uint16 -- the
            # array form _parse_code_list tries first.
            codes = list(self.properties)
            return ResponseCode.OK, struct.pack("<I", len(codes)) + b"".join(
                struct.pack("<H", c) for c in codes
            )
        if opcode == OperationCode.GET_DEVICE_PROP_DESC:
            code = params[0] if params else 0
            if code in self.properties:
                # The descriptor speaks scalar values; the shutter pair and
                # other long forms report their first four bytes.
                value = int.from_bytes(self.properties[code][:4], "little")
                desc = PropertyDesc(
                    code=code,
                    data_type=DataType.UINT32,
                    access=AccessCapability.GET_SET,
                    form_flag=FormFlag.NONE,
                    default_value=value,
                    current_value=value,
                )
                return ResponseCode.OK, desc.pack()
            return ResponseCode.OPERATION_NOT_SUPPORTED, b""
        if opcode == OperationCode.GET_STORAGE_IDS:
            ids = [0x50000001]
            return ResponseCode.OK, struct.pack("<I", len(ids)) + b"".join(
                struct.pack("<I", i) for i in ids
            )
        if opcode == OperationCode.GET_STORAGE_INFO:
            sid = params[0] if params else 0
            info = StorageInfo(
                storage_id=sid,
                storage_type=0x0003,
                access_capability=0x0003,
                max_capacity=32 * 1024**3,
                free_space_bytes=28 * 1024**3,
                free_space_objects=12345,
            )
            return ResponseCode.OK, info.pack()
        return ResponseCode.OPERATION_NOT_SUPPORTED, b""

    def _object_info(self, handle: int, blob: bytes) -> bytes:
        """Pack a PTP ObjectInfo dataset for one stored object."""

        def ptp_string(text: str) -> bytes:
            return bytes([len(text)]) + text.encode("utf-16-le") + b"\x00\x00"

        # StorageID, ObjectFormat (JPEG), ProtectionStatus, CompressedSize,
        # then the thumb/image fields the download path never reads.
        head = struct.pack(
            "<IHHIHIIIIIIIIHI",
            0x50000001,
            0x3801,
            0,
            len(blob),
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
        )
        name = self.filenames.get(handle, "DSC_UNKNOWN.JPG")
        return head + ptp_string(name) + ptp_string("20260825T220000")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Fake Nikon PTP/IP camera.")
    parser.add_argument("--bind", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO)

    server = SimulatorServer(args.bind, args.port)
    print(f"simulated camera on {args.bind}:{args.port} (ctrl-c to stop)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
