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

from .nikon import NikonOperation, NikonProperty
from .ptp import DeviceInfo, OperationCode, ResponseCode, VendorExtension
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
    OperationCode.GET_OBJECT_HANDLES,
    OperationCode.GET_OBJECT,
    OperationCode.GET_THUMB,
    OperationCode.INITIATE_CAPTURE,
    OperationCode.GET_DEVICE_PROP_DESC,
    OperationCode.GET_DEVICE_PROP_VALUE,
    OperationCode.SET_DEVICE_PROP_VALUE,
    OperationCode.GET_PARTIAL_OBJECT,
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
    try:
        import io

        from PIL import Image, ImageDraw
    except ImportError:
        return b"\xff\xd8\xff" + b"skyshutter simulated frame" + b"\xff\xd9"
    image = Image.new("RGB", (640, 480), (24, 24, 32))
    ImageDraw.Draw(image).text((20, 20), "skyshutter simulator", fill=(220, 220, 220))
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
            0x500F,
            0x5010,
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
        _, opcode, transaction_id = struct.unpack("<IHI", packet.payload[:10])
        # Parameters follow the ten header bytes, four bytes each. Property
        # reads need them -- without, every property looks like the same one.
        raw = packet.payload[10:]
        params = tuple(
            struct.unpack_from("<I", raw, offset)[0] for offset in range(0, len(raw) - 3, 4)
        )
        code, data = self.server.operation(opcode, params)
        log.info("operation 0x%04X -> 0x%04X (%d bytes)", opcode, code, len(data))
        if data:
            send_packet(
                sock, Packet(PacketType.START_DATA, struct.pack("<IQ", transaction_id, len(data)))
            )
            send_packet(
                sock, Packet(PacketType.END_DATA, struct.pack("<I", transaction_id) + data)
            )
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
        #: Vendor properties the real camera reports. The prohibit condition
        #: starts clear -- a simulator with the lens retracted would be useless.
        self.properties: dict[int, int] = {
            NikonProperty.LIVE_VIEW_STATUS: 0,
            NikonProperty.LIVE_VIEW_PROHIBIT: 0,
            NikonProperty.SHUTTER_SPEED: 0,
            NikonProperty.REMAINING_CAPTURE: 999,
            NikonProperty.LENS_FOCAL_MIN: 24,
            NikonProperty.LENS_FOCAL_MAX: 3000,
        }

    def operation(self, opcode: int, params: tuple[int, ...] = ()) -> tuple[int, bytes]:
        if opcode == OperationCode.GET_DEVICE_INFO:
            return ResponseCode.OK, self.device_info.pack()
        if opcode == OperationCode.GET_DEVICE_PROP_VALUE:
            code = params[0] if params else 0
            if code in self.properties:
                return ResponseCode.OK, struct.pack("<I", self.properties[code])
            return ResponseCode.OPERATION_NOT_SUPPORTED, b""
        if opcode == OperationCode.GET_PARTIAL_OBJECT:
            # (handle, offset, length) -- hand back that slice of the frame.
            _, offset, length = (*params, 0, 0, 0)[:3]
            return ResponseCode.OK, self.frame[offset : offset + length]
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
        if opcode in (
            OperationCode.INITIATE_CAPTURE,
            NikonOperation.CAPTURE,
            NikonOperation.INITIATE_CAPTURE_REC_IN_MEDIA,
            NikonOperation.AF_DRIVE,
        ):
            self.captures += 1
            return ResponseCode.OK, b""
        return ResponseCode.OPERATION_NOT_SUPPORTED, b""


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
