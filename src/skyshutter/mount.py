"""SynScan motor client (UDP) for the AZ-GTi mount.

Speaks the SynScan MC serial protocol tunneled through the mount's WiFi
module on UDP 11880.  Framing (measured 27.08.2026, see docs/FINDINGS.md):

* command: ``:<cmd><axis><hex data>\\r`` — CR terminator, no ``#``
* response: ``=<hex data>\\r`` or ``!<error>\\r``
* multi-byte values travel little-endian in byte-pairs: 0x123456 as "563412"

Reference cross-check: pysynscan (github.com/nachoplus/pysynscan), verified
against live responses (``:F3``, ``:e``, ``:a``, ``:s``, ``:j``, ``:f``).
This module is an independent stdlib-only implementation.

Read-only commands are always allowed.  Every command that moves the mount
(``set_position_counts``, ``set_motion_mode``, ``set_step_period``,
``start``, ``stop``) raises :class:`MotionDeniedError` unless the client
was constructed with ``allow_motion=True`` — mirroring the camera rule
that writes need an explicit go per playbook.md §7.
"""

from __future__ import annotations

import os
import socket
from dataclasses import dataclass
from typing import Any, Protocol

DEFAULT_HOST = "192.168.4.1"
DEFAULT_PORT = 11880
DEFAULT_TIMEOUT = 3.0

ENV_MOUNT_HOST = "SKYSHUTTER_MOUNT_HOST"
ENV_MOUNT_PORT = "SKYSHUTTER_MOUNT_PORT"

CR = b"\r"
#: the mount reports axis positions offset by this value (mid-range)
POSITION_OFFSET = 0x800000

ERROR_NAMES: dict[int, str] = {
    0: "unknown command",
    1: "command length error",
    2: "motor not stopped",
    3: "invalid character",
    4: "not initialized",
    5: "driver sleeping",
    7: "PEC training running",
    8: "no valid PEC data",
}

AXIS_AZ = 1
AXIS_ALT = 2
AXES = (AXIS_AZ, AXIS_ALT)


def mount_host(override: str | None = None) -> str:
    return override or os.environ.get(ENV_MOUNT_HOST) or DEFAULT_HOST


def mount_port(override: int | None = None) -> int:
    return override or int(os.environ.get(ENV_MOUNT_PORT, "0")) or DEFAULT_PORT


class SynscanError(RuntimeError):
    """Base class for mount communication failures."""


class SynscanTimeoutError(SynscanError):
    """No UDP response within the configured timeout."""


class SynscanCommandError(SynscanError):
    """The mount answered with an error (``!<n>``)."""

    def __init__(self, code: int, response: bytes) -> None:
        self.code = code
        self.response = response
        super().__init__(f"mount error {code} ({ERROR_NAMES.get(code, 'unknown')}): {response!r}")


class MotionDeniedError(SynscanError):
    """A motion command was attempted while ``allow_motion`` is off."""


def encode_value(value: int, ndigits: int) -> str:
    """Encode an integer as synscan hex (byte-pairs reversed).

    0x123456 with ndigits=6 becomes "563412"; ndigits=0 yields "".
    """
    if ndigits not in (0, 1, 2, 4, 6):
        raise ValueError(f"ndigits must be 0, 1, 2, 4 or 6, got {ndigits}")
    text = f"{value:0{ndigits}X}" if ndigits else ""
    return "".join(text[i : i + 2] for i in range(len(text) - 2, -1, -2))


def decode_value(payload: bytes) -> int | str:
    """Decode a ``=...`` payload.

    Returns "" for empty payloads, the raw 3-digit string for status words
    (12-bit values have odd length and no defined pair order), and the
    byte-pair-reversed integer otherwise.
    """
    text = payload.decode("ascii", errors="replace")
    if len(text) == 0:
        return ""
    if len(text) % 2 == 1:
        return text
    swapped = "".join(text[i : i + 2] for i in range(len(text) - 2, -1, -2))
    return int(swapped, 16)


@dataclass(frozen=True)
class AxisStatus:
    axis: int
    position_counts: int
    status_word: str
    tracking: bool
    counter_clockwise: bool
    fast_speed: bool
    running: bool
    blocked: bool
    init_done: bool


@dataclass(frozen=True)
class MountSnapshot:
    host: str
    initialized: bool
    version: int
    steps_per_rev: int
    timer_freq: int
    axes: tuple[AxisStatus, ...]


def decode_status_word(word: str) -> dict[str, bool]:
    """Decode the 3-hex-digit status word (see docs/FINDINGS.md).

    Digit 1: bit0 tracking/goto, bit1 CCW, bit2 fast.
    Digit 2: bit0 running, bit1 blocked.
    Digit 3: bit0 clear = init done (the :F3 cross-check on the real mount
    confirms the code reading in pysynscan, not its docstring).
    """
    if len(word) != 3:
        raise ValueError(f"status word must be 3 hex digits, got {word!r}")
    a, b, c = (int(ch, 16) for ch in word)
    return {
        "tracking": bool(a & 0x01),
        "counter_clockwise": bool(a & 0x02),
        "fast_speed": bool(a & 0x04),
        "running": bool(b & 0x01),
        "blocked": bool(b & 0x02),
        "init_done": not (c & 0x01),
    }


class DatagramSock(Protocol):
    """Minimal surface SynscanClient needs (real socket or test double)."""

    def sendto(self, data: bytes, address: Any, /) -> None: ...

    def recvfrom(self, bufsize: int, /) -> tuple[bytes, Any]: ...


def _udp_socket(timeout: float) -> Any:
    """Build the default UDP socket (Any keeps socket overloads out of the Protocol)."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(timeout)
    return sock


class SynscanClient:
    """UDP client for the SynScan motor controller."""

    def __init__(
        self,
        host: str | None = None,
        port: int | None = None,
        timeout: float = DEFAULT_TIMEOUT,
        allow_motion: bool = False,
        sock: DatagramSock | None = None,
    ) -> None:
        self.host = mount_host(host)
        self.port = mount_port(port)
        self.timeout = timeout
        self.allow_motion = allow_motion
        self._sock = sock if sock is not None else _udp_socket(timeout)

    # -- protocol core ------------------------------------------------

    def transact_raw(self, message: bytes) -> bytes:
        """Send a pre-built command and return the payload after ``=``.

        Raises :class:`SynscanCommandError` for ``!`` responses and
        :class:`SynscanTimeoutError` when the mount stays silent.
        """
        self._sock.sendto(message, (self.host, self.port))
        try:
            response, _addr = self._sock.recvfrom(1024)
        except TimeoutError:
            raise SynscanTimeoutError(
                f"no response to {message!r} within {self.timeout}s"
            ) from None
        except OSError as exc:
            raise SynscanTimeoutError(f"{exc} while waiting for {message!r}") from exc
        if not response:
            raise SynscanCommandError(-1, response)
        body = response[:-1] if response.endswith(CR) else response
        if body[:1] == b"=":
            return body[1:]
        if body[:1] == b"!":
            code_text = body[1:].decode("ascii", errors="replace")
            try:
                code = int(code_text, 16) if code_text else -1
            except ValueError:
                code = -1
            raise SynscanCommandError(code, response)
        raise SynscanCommandError(-1, response)

    def transact(self, cmd: str, axis: int, data: int | None = None, ndigits: int = 0) -> bytes:
        """Send ``:<cmd><axis><data>\\r`` and return the payload after ``=``."""
        if len(cmd) != 1:
            raise ValueError(f"command must be a single letter, got {cmd!r}")
        if axis not in AXES:
            raise ValueError(f"axis must be one of {AXES}, got {axis}")
        payload = encode_value(data, ndigits) if data is not None else ""
        message = (
            b":" + cmd.encode("ascii") + str(axis).encode("ascii") + payload.encode("ascii") + CR
        )
        return self.transact_raw(message)

    # -- read-only interface ------------------------------------------

    def is_initialized(self) -> bool:
        """:F3 — axis-free probe; answers bare ``=`` once initialized."""
        return self.transact_raw(b":F3" + CR) == b""

    def version(self, axis: int = AXIS_AZ) -> int:
        return self._query("e", axis)  # type: ignore[return-value]

    def steps_per_rev(self, axis: int = AXIS_AZ) -> int:
        return self._query("a", axis)  # type: ignore[return-value]

    def timer_freq(self, axis: int = AXIS_AZ) -> int:
        return self._query("s", axis)  # type: ignore[return-value]

    def position_counts(self, axis: int = AXIS_AZ) -> int:
        """:j — signed axis position, un-offset from 0x800000."""
        return self._query("j", axis) - POSITION_OFFSET  # type: ignore[operator]

    def status_word(self, axis: int = AXIS_AZ) -> str:
        return str(self._query("f", axis))

    def axis_status(self, axis: int = AXIS_AZ) -> AxisStatus:
        bits = decode_status_word(self.status_word(axis))
        return AxisStatus(
            axis=axis,
            position_counts=self.position_counts(axis),
            status_word=self.status_word(axis),
            **bits,
        )

    def snapshot(self) -> MountSnapshot:
        axes = tuple(self.axis_status(axis) for axis in AXES)
        return MountSnapshot(
            host=self.host,
            initialized=self.is_initialized(),
            version=self.version(),
            steps_per_rev=self.steps_per_rev(),
            timer_freq=self.timer_freq(),
            axes=axes,
        )

    def _query(self, cmd: str, axis: int) -> int | str:
        return decode_value(self.transact(cmd, axis))

    # -- motion interface (gated) --------------------------------------

    def _require_motion(self) -> None:
        if not self.allow_motion:
            raise MotionDeniedError(
                "motion commands require SynscanClient(allow_motion=True) — "
                "explicit go per playbook.md §7"
            )

    def set_position_counts(self, axis: int, counts: int) -> None:
        """:E — set the axis position counter (mount must be stopped)."""
        self._require_motion()
        self.transact("E", axis, counts + POSITION_OFFSET, ndigits=6)

    def set_motion_mode(self, axis: int, mode: int) -> None:
        """:G — set motion mode (2-digit mode word; semantics per SynScan MC
        protocol, deliberately not guessed here)."""
        self._require_motion()
        self.transact("G", axis, mode, ndigits=2)

    def set_step_period(self, axis: int, period: int) -> None:
        """:I — set the step timer period (speed); 0 means fastest."""
        self._require_motion()
        self.transact("I", axis, period, ndigits=6)

    def start(self, axis: int) -> None:
        """:J — start moving with the configured mode/period."""
        self._require_motion()
        self.transact("J", axis)

    def stop(self, axis: int, hard: bool = False) -> None:
        """:K (decelerate) or :L (instant) stop for one axis."""
        self._require_motion()
        self.transact("L" if hard else "K", axis)

    def stop_all(self, hard: bool = False) -> None:
        """Safety stop: decelerate (or hard-stop) both axes."""
        self._require_motion()
        for axis in AXES:
            self.transact("L" if hard else "K", axis)
