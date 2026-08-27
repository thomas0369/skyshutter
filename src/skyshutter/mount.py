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

# Motion-mode word (pysynscan motors.py semantics, verified against its
# axis_set_motion_mode construction):
#   digit1 bit0 = tracking(1)/goto(0), bit1 = speed (inverted between the
#   two modes), digit2 bit0 = CCW.  Values below are the base words.
MODE_GOTO = 0x00  # + 0x20 -> slow goto, + 0x01 -> CCW
MODE_TRACK = 0x10  # + 0x20 -> fast tracking, + 0x01 -> CCW
#: default breakpoint increment :M (pysynscan default)
DEFAULT_BREAKSTEP = 0x0DAC


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


def encode_value(value: int, ndigits: int = 6) -> str:
    """Encode an integer as synscan hex (byte-pairs reversed).

    0x123456 with ndigits=6 becomes "563412"; ndigits=0 yields "".
    """
    if ndigits not in (0, 1, 2, 4, 6):
        raise ValueError(f"ndigits must be 0, 1, 2, 4 or 6, got {ndigits}")
    text = f"{value:0{ndigits}X}" if ndigits else ""
    if len(text) % 2:  # single digit: no byte pairs to swap
        return text
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
        self._steps_per_rev: int | None = None
        self._timer_freq: int | None = None
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
        word = self.status_word(axis)
        bits = decode_status_word(word)
        return AxisStatus(
            axis=axis,
            position_counts=self.position_counts(axis),
            status_word=word,
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
        self.transact("I", axis, max(1, period), ndigits=6)

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

    # -- goto / targets (gated) ----------------------------------------

    def initialize_axis(self, axis: int) -> None:
        """:F — (re)initialize one motor controller (:F1/:F2).

        The controller falls back to tracking mode after this; also the
        first thing to try against the `alt init=False` status word.
        """
        self._require_motion()
        self.transact("F", axis)

    def set_goto_target_counts(self, axis: int, target: int) -> None:
        """:S — goto target position (0x800000-offset like :E)."""
        self._require_motion()
        self.transact("S", axis, target + POSITION_OFFSET, ndigits=6)

    def set_goto_increment(self, axis: int, increment: int) -> None:
        """:H — remaining position for the slow-goto approach phase."""
        self._require_motion()
        self.transact("H", axis, increment + POSITION_OFFSET, ndigits=6)

    def set_breakstep(self, axis: int, breakstep: int = 0x0DAC) -> None:
        """:M — breakpoint increment (distance at which slow-goto decelerates)."""
        self._require_motion()
        self.transact("M", axis, breakstep, ndigits=6)

    def set_switch(self, on: bool) -> None:
        """:O — auxiliary switch on the mount (e.g. camera power)."""
        self._require_motion()
        self.transact("O", AXIS_AZ, 1 if on else 0, ndigits=1)

    # -- calibration cache + degree layer -------------------------------

    def _calibration(self) -> tuple[int, int]:
        """Lazy (steps_per_rev, timer_freq) — one :a/:s round trip per axis 1."""
        if self._steps_per_rev is None or self._timer_freq is None:
            self._steps_per_rev = self.steps_per_rev()
            self._timer_freq = self.timer_freq()
        return self._steps_per_rev, self._timer_freq

    def degrees2counts(self, degrees: float) -> float:
        steps, _timer = self._calibration()
        return degrees * steps / 360.0

    def counts2degrees(self, counts: float) -> float:
        steps, _timer = self._calibration()
        return counts * 360.0 / steps

    def dps2period(self, degrees_per_second: float) -> int:
        """Convert deg/s to a step-timer period (14400 Hz / counts per second)."""
        steps, timer = self._calibration()
        counts_per_second = abs(degrees_per_second) * steps / 360.0
        if counts_per_second <= 0:
            return timer  # slowest possible period == standstill in tracking
        return max(1, int(timer / counts_per_second))

    def period2dps(self, period: int) -> float:
        steps, timer = self._calibration()
        return timer / period * 360.0 / steps

    def position_degrees(self, axis: int) -> float:
        return self.counts2degrees(self.position_counts(axis))

    def set_position_degrees(self, axis: int, degrees: float) -> None:
        self.set_position_counts(axis, round(self.degrees2counts(degrees)))

    # -- high level moves (gated) ---------------------------------------

    def track_mode(self, axis: int, ccw: bool = False, fast: bool = False) -> None:
        """:G — tracking mode word (0x10 | 0x20*fast | 0x01*ccw)."""
        self.set_motion_mode(axis, MODE_TRACK | (0x20 if fast else 0) | (0x01 if ccw else 0))

    def goto_mode(self, axis: int, ccw: bool = False, fast: bool = False) -> None:
        """:G — goto mode word; note the speed bit is inverted vs. tracking."""
        self.set_motion_mode(axis, MODE_GOTO | (0x00 if fast else 0x20) | (0x01 if ccw else 0))

    def slew(self, axis: int, degrees_per_second: float) -> None:
        """Move one axis at a signed speed, switching direction safely.

        While the axis already runs in tracking mode in the wanted
        direction, only the :I period changes — no stop/start hop. That is
        what keeps satellite tracking smooth. Sign: negative = CCW.
        """
        self._require_motion()
        if degrees_per_second == 0:
            self.stop(axis)
            return
        ccw = degrees_per_second < 0
        status = self.axis_status(axis)
        if status.running and (not status.tracking or status.counter_clockwise != ccw):
            self.stop(axis)
            status = self.axis_status(axis)
        if not status.running:
            self.track_mode(axis, ccw=ccw)
        self.set_step_period(axis, self.dps2period(degrees_per_second))
        if not status.running:
            self.start(axis)

    def slew_both(self, az_dps: float, alt_dps: float) -> None:
        self.slew(AXIS_AZ, az_dps)
        self.slew(AXIS_ALT, alt_dps)

    def goto_degrees(self, axis: int, target_degrees: float) -> None:
        """Classic goto: stop, direction-aware goto mode, :S target, :J."""
        self._require_motion()
        self.stop(axis)
        current = self.position_degrees(axis)
        ccw = target_degrees < current
        self.goto_mode(axis, ccw=ccw, fast=True)
        self.set_goto_target_counts(axis, round(self.degrees2counts(target_degrees)))
        self.start(axis)

    def sync_degrees(self, az_degrees: float, alt_degrees: float) -> None:
        """:E both axes — tell the mount where it currently points."""
        self.set_position_degrees(AXIS_AZ, az_degrees)
        self.set_position_degrees(AXIS_ALT, alt_degrees)
