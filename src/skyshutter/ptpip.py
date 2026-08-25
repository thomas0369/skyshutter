"""PTP/IP transport: PTP over TCP port 15740.

Frame layout (all little endian)::

    +0  uint32  length, including these 8 header bytes
    +4  uint32  packet type
    +8  payload

The packet types and payload offsets follow the PTP/IP annex of ISO 15740 and
match what ``libgphoto2/camlibs/ptp2/ptpip.c`` implements, which is the only
widely deployed reference for Nikon's flavour of PTP/IP.
"""

from __future__ import annotations

import logging
import select
import socket
import struct
import uuid
from dataclasses import dataclass
from enum import IntEnum

from .ptp import OperationCode, PtpError, ResponseCode

log = logging.getLogger(__name__)

DEFAULT_PORT = 15740
HEADER_SIZE = 8
PROTOCOL_VERSION = 0x00010000
MAX_PACKET_SIZE = 64 * 1024 * 1024


def encode_utf16(value: str) -> bytes:
    """NUL terminated UTF-16LE, the string form used by PTP/IP handshakes."""
    return (value + "\x00").encode("utf-16-le")


def decode_utf16(raw: bytes) -> str:
    """Decode a NUL terminated UTF-16LE string, ignoring trailing garbage."""
    usable = raw[: len(raw) // 2 * 2]
    return usable.decode("utf-16-le", "replace").split("\x00")[0]


class PacketType(IntEnum):
    INIT_COMMAND_REQUEST = 1
    INIT_COMMAND_ACK = 2
    INIT_EVENT_REQUEST = 3
    INIT_EVENT_ACK = 4
    INIT_FAIL = 5
    OPERATION_REQUEST = 6
    OPERATION_RESPONSE = 7
    EVENT = 8
    START_DATA = 9
    DATA = 10
    CANCEL = 11
    END_DATA = 12
    PING = 13
    PONG = 14


class DataPhase(IntEnum):
    NONE_OR_IN = 1
    OUT = 2


@dataclass(frozen=True)
class Packet:
    type: int
    payload: bytes = b""

    def encode(self) -> bytes:
        return struct.pack("<II", HEADER_SIZE + len(self.payload), self.type) + self.payload

    @property
    def type_name(self) -> str:
        try:
            return PacketType(self.type).name
        except ValueError:
            return f"UNKNOWN(0x{self.type:08X})"


@dataclass(frozen=True)
class Transaction:
    """Result of a completed PTP transaction."""

    response_code: int
    parameters: tuple[int, ...] = ()
    data: bytes = b""

    @property
    def ok(self) -> bool:
        return self.response_code == ResponseCode.OK


class PtpIpError(RuntimeError):
    """Transport level failure (framing, handshake, connection loss)."""


def _recv_exactly(sock: socket.socket, size: int) -> bytes:
    chunks: list[bytes] = []
    received = 0
    while received < size:
        chunk = sock.recv(min(65536, size - received))
        if not chunk:
            raise PtpIpError(f"connection closed after {received} of {size} bytes")
        chunks.append(chunk)
        received += len(chunk)
    return b"".join(chunks)


def read_packet(sock: socket.socket) -> Packet:
    header = _recv_exactly(sock, HEADER_SIZE)
    length, ptype = struct.unpack("<II", header)
    if length < HEADER_SIZE:
        raise PtpIpError(f"invalid packet length {length}")
    if length > MAX_PACKET_SIZE:
        raise PtpIpError(f"refusing packet of {length} bytes")
    payload = _recv_exactly(sock, length - HEADER_SIZE) if length > HEADER_SIZE else b""
    packet = Packet(ptype, payload)
    log.debug("recv %s (%d bytes)", packet.type_name, length)
    return packet


def send_packet(sock: socket.socket, packet: Packet) -> None:
    log.debug("send %s (%d bytes)", packet.type_name, HEADER_SIZE + len(packet.payload))
    sock.sendall(packet.encode())


def encode_operation_request(
    opcode: int,
    transaction_id: int,
    params: tuple[int, ...] = (),
    data_phase: int = DataPhase.NONE_OR_IN,
) -> Packet:
    if len(params) > 5:
        raise ValueError("PTP allows at most 5 operation parameters")
    payload = struct.pack("<IHI", data_phase, opcode, transaction_id)
    payload += b"".join(struct.pack("<I", p) for p in params)
    return Packet(PacketType.OPERATION_REQUEST, payload)


def decode_operation_response(packet: Packet) -> tuple[int, int, tuple[int, ...]]:
    if len(packet.payload) < 6:
        raise PtpIpError("short operation response")
    code, transaction_id = struct.unpack("<HI", packet.payload[:6])
    rest = packet.payload[6:]
    params = struct.unpack(f"<{len(rest) // 4}I", rest[: len(rest) // 4 * 4])
    return code, transaction_id, params


class PtpIpConnection:
    """A command + event connection pair to a PTP/IP responder."""

    def __init__(
        self,
        host: str,
        port: int = DEFAULT_PORT,
        guid: uuid.UUID | None = None,
        friendly_name: str = "skyshutter",
        timeout: float = 10.0,
    ) -> None:
        self.host = host
        self.port = port
        self.guid = guid or uuid.uuid4()
        self.friendly_name = friendly_name
        self.timeout = timeout

        self._command: socket.socket | None = None
        self._event: socket.socket | None = None
        self._transaction_id = 0

        self.connection_number: int | None = None
        self.responder_guid: uuid.UUID | None = None
        self.responder_name: str = ""

    # -- lifecycle ---------------------------------------------------------

    def connect(self, with_events: bool = True) -> None:
        self._command = self._open_socket()
        self._init_command_connection()
        if with_events:
            try:
                self._event = self._open_socket()
                self._init_event_connection()
            except OSError as exc:  # event channel is optional for shooting
                log.warning("event connection unavailable: %s", exc)
                self._close(self._event)
                self._event = None

    def close(self) -> None:
        self._close(self._event)
        self._close(self._command)
        self._event = None
        self._command = None

    def __enter__(self) -> PtpIpConnection:
        self.connect()
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    @staticmethod
    def _close(sock: socket.socket | None) -> None:
        if sock is not None:
            try:
                sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            sock.close()

    def _open_socket(self) -> socket.socket:
        sock = socket.create_connection((self.host, self.port), timeout=self.timeout)
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        return sock

    # -- handshake ---------------------------------------------------------

    def _init_command_connection(self) -> None:
        assert self._command is not None
        # The GUID travels as 16 raw bytes.  RFC 4122 byte order is used so
        # that ``str(guid)`` matches the hex order seen in a packet capture.
        payload = self.guid.bytes + encode_utf16(self.friendly_name)
        payload += struct.pack("<I", PROTOCOL_VERSION)
        send_packet(self._command, Packet(PacketType.INIT_COMMAND_REQUEST, payload))

        packet = read_packet(self._command)
        if packet.type == PacketType.INIT_FAIL:
            reason = struct.unpack("<I", packet.payload[:4])[0] if len(packet.payload) >= 4 else -1
            raise PtpIpError(
                f"camera rejected the connection (InitFail reason 0x{reason:08X}). "
                "The GUID is probably not paired, or another client holds the session."
            )
        if packet.type != PacketType.INIT_COMMAND_ACK:
            raise PtpIpError(f"expected InitCommandAck, got {packet.type_name}")

        body = packet.payload
        if len(body) < 20:
            raise PtpIpError("short InitCommandAck")
        self.connection_number = struct.unpack("<I", body[:4])[0]
        self.responder_guid = uuid.UUID(bytes=body[4:20])
        self.responder_name = decode_utf16(body[20:])
        log.info(
            "connected to %r (connection %d, guid %s)",
            self.responder_name,
            self.connection_number,
            self.responder_guid,
        )

    def _init_event_connection(self) -> None:
        assert self._event is not None
        if self.connection_number is None:
            raise PtpIpError("command connection must be established first")
        send_packet(
            self._event,
            Packet(PacketType.INIT_EVENT_REQUEST, struct.pack("<I", self.connection_number)),
        )
        packet = read_packet(self._event)
        if packet.type != PacketType.INIT_EVENT_ACK:
            raise PtpIpError(f"expected InitEventAck, got {packet.type_name}")

    # -- transactions ------------------------------------------------------

    def next_transaction_id(self) -> int:
        self._transaction_id = (self._transaction_id + 1) & 0xFFFFFFFF
        return self._transaction_id

    def transaction(
        self,
        opcode: int,
        params: tuple[int, ...] = (),
        data: bytes | None = None,
        raise_on_error: bool = True,
    ) -> Transaction:
        """Run one PTP operation and return its response (and any data-in)."""
        if self._command is None:
            raise PtpIpError("not connected")

        try:
            transaction_id = self.next_transaction_id()
            phase = DataPhase.OUT if data is not None else DataPhase.NONE_OR_IN
            send_packet(
                self._command, encode_operation_request(opcode, transaction_id, params, phase)
            )

            if data is not None:
                send_packet(
                    self._command,
                    Packet(PacketType.START_DATA, struct.pack("<IQ", transaction_id, len(data))),
                )
                send_packet(
                    self._command,
                    Packet(PacketType.END_DATA, struct.pack("<I", transaction_id) + data),
                )

            received = bytearray()
            expected_length: int | None = None
            while True:
                packet = read_packet(self._command)
                if packet.type == PacketType.START_DATA:
                    expected_length = struct.unpack("<Q", packet.payload[4:12])[0]
                elif packet.type == PacketType.DATA:
                    received += packet.payload[4:]
                elif packet.type == PacketType.END_DATA:
                    received += packet.payload[4:]
                elif packet.type == PacketType.OPERATION_RESPONSE:
                    code, _, response_params = decode_operation_response(packet)
                    break
                elif packet.type == PacketType.PING:
                    send_packet(self._command, Packet(PacketType.PONG))
                elif packet.type == PacketType.EVENT:
                    log.debug("event on command channel: %s", packet.payload.hex())
                else:
                    raise PtpIpError(f"unexpected {packet.type_name} during transaction")
        except (OSError, PtpIpError):
            self.close()
            raise

        if expected_length is not None and len(received) != expected_length:
            log.warning(
                "data phase length mismatch: announced %d, received %d",
                expected_length,
                len(received),
            )

        result = Transaction(code, tuple(response_params), bytes(received))
        if raise_on_error and not result.ok:
            raise PtpError(code, opcode)
        return result

    # -- events ------------------------------------------------------------

    def poll_event(self, timeout: float = 0.0) -> Packet | None:
        """Return the next packet from the event channel, if one is pending."""
        if self._event is None:
            return None
        readable, _, _ = select.select([self._event], [], [], timeout)
        if not readable:
            return None
        return read_packet(self._event)

    # -- convenience -------------------------------------------------------

    def open_session(self, session_id: int = 1) -> None:
        """Open a session, treating an already-open one as success.

        The vendor app accepts ``SessionAlreadyOpen`` exactly like ``OK`` and
        carries on with the id it just asked for, rather than closing and
        reopening. Doing anything else here turns a harmless reconnect into a
        failure.
        """
        result = self.transaction(OperationCode.OPEN_SESSION, (session_id,), raise_on_error=False)
        if not result.ok and result.response_code != ResponseCode.SESSION_ALREADY_OPEN:
            raise PtpError(result.response_code, OperationCode.OPEN_SESSION)

    def ping(self) -> None:
        """Send a probe over the event channel, as the vendor app does.

        Measured in the app: every nine seconds, on the *event* socket, and it
        expects the answer within ten. Answering someone else's ping is not
        enough -- nothing else keeps the link alive.
        """
        if self._event is None:
            return
        try:
            send_packet(self._event, Packet(PacketType.PING))
        except OSError as exc:
            log.warning("failed to send ping on event channel: %s", exc)
            self.close()

    def close_session(self) -> None:
        self.transaction(OperationCode.CLOSE_SESSION, raise_on_error=False)
