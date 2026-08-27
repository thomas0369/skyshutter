"""Tests for the SynScan mount client (protocol core, gate, loopback sim)."""

from __future__ import annotations

import socket
import threading
from collections.abc import Iterator

import pytest

from skyshutter.mount import (
    AXIS_ALT,
    AXIS_AZ,
    CR,
    MotionDeniedError,
    SynscanClient,
    SynscanCommandError,
    SynscanTimeoutError,
    decode_status_word,
    decode_value,
    encode_value,
)

# Live values measured 27.08.2026 against the AZ-GTi (docs/FINDINGS.md)
LIVE_VERSION = "0336C5"
LIVE_STEPS = "00A41F"  # byte-swapped 0x1FA400 = 2073600 steps/rev
LIVE_TIMER = "403800"  # 0x003840 = 14400 Hz
LIVE_J = "000080"  # 0x800000 -> position offset
LIVE_F = ("100", "101")


class FakeSock:
    """Records sendto() and replies with a canned response."""

    def __init__(self, response: bytes) -> None:
        self.response = response
        self.sent: list[tuple[bytes, tuple]] = []

    def sendto(self, data: bytes, addr: tuple) -> None:
        self.sent.append((data, addr))

    def recvfrom(self, size: int) -> tuple[bytes, tuple]:
        return self.response, ("192.168.4.1", 11880)


class TimeoutSock(FakeSock):
    def recvfrom(self, size: int) -> tuple[bytes, tuple]:
        raise TimeoutError("timed out")


def test_encode_value_swaps_byte_pairs() -> None:
    assert encode_value(0x123456, 6) == "563412"
    assert encode_value(0x1234, 4) == "3412"
    assert encode_value(0x12, 2) == "12"
    assert encode_value(0, 6) == "000000"
    assert encode_value(5, 0) == ""
    with pytest.raises(ValueError):
        encode_value(1, 3)


def test_decode_value_roundtrip_and_status_words() -> None:
    assert decode_value(b"563412") == 0x123456
    assert decode_value(b"3412") == 0x1234
    assert decode_value(b"") == ""
    # odd length = 12-bit status word, returned verbatim
    assert decode_value(b"100") == "100"
    assert (
        decode_value(
            encode_value(0x0DAC, 6).encode(),
        )
        == 0x0DAC
    )


def test_decode_status_word_matches_live_readings() -> None:
    # axis 1 standing, tracking mode, initialized (verified via :F3 == '=')
    bits = decode_status_word(LIVE_F[0])
    assert bits == {
        "tracking": True,
        "counter_clockwise": False,
        "fast_speed": False,
        "running": False,
        "blocked": False,
        "init_done": True,
    }
    with pytest.raises(ValueError):
        decode_status_word("1000")


def test_client_builds_correct_frames() -> None:
    sock = FakeSock(b"=" + LIVE_VERSION.encode() + CR)
    client = SynscanClient(sock=sock, timeout=1.0)
    assert client.version() == decode_value(LIVE_VERSION.encode())
    assert sock.sent[0][0] == b":e1" + CR


def test_client_error_response_raises() -> None:
    sock = FakeSock(b"!3" + CR)
    client = SynscanClient(sock=sock)
    with pytest.raises(SynscanCommandError) as excinfo:
        client.version()
    assert excinfo.value.code == 3
    assert "invalid character" in str(excinfo.value)


def test_client_timeout_raises() -> None:
    client = SynscanClient(sock=TimeoutSock(b""), timeout=0.01)
    with pytest.raises(SynscanTimeoutError):
        client.status_word()


def test_motion_gate_denies_by_default() -> None:
    client = SynscanClient(sock=FakeSock(b"=" + CR))
    gated = (
        lambda: client.stop(AXIS_AZ),
        lambda: client.start(AXIS_AZ),
        lambda: client.set_step_period(AXIS_AZ, 100),
        lambda: client.set_position_counts(AXIS_AZ, 0),
        lambda: client.set_motion_mode(AXIS_AZ, 0x10),
        lambda: client.stop_all(),
    )
    for call in gated:
        with pytest.raises(MotionDeniedError):
            call()


def test_motion_allowed_sends_frames() -> None:
    sock = FakeSock(b"=" + CR)
    client = SynscanClient(sock=sock, allow_motion=True)
    client.set_position_counts(AXIS_AZ, 0x1000)
    client.set_motion_mode(AXIS_AZ, 0x10)
    client.set_step_period(AXIS_AZ, 0x0DAC)
    client.start(AXIS_AZ)
    client.stop(AXIS_AZ)
    client.stop_all(hard=True)
    frames = [data for data, _addr in sock.sent]
    assert frames[0] == b":E1" + encode_value(0x801000, 6).encode() + CR
    assert frames[1] == b":G110" + CR
    assert frames[2] == b":I1" + encode_value(0x0DAC, 6).encode() + CR
    assert frames[3] == b":J1" + CR
    assert frames[4] == b":K1" + CR
    assert frames[5:] == [b":L1" + CR, b":L2" + CR]


# -- loopback "mount simulator": replies like the AZ-GTi measured today --


class MountSim:
    """UDP server imitating the AZ-GTi: reads return live state, writes
    mutate it, every incoming frame is logged for sequence assertions."""

    def __init__(self) -> None:
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(("127.0.0.1", 0))
        self.sock.settimeout(2.0)
        self.addr = self.sock.getsockname()
        self.received: list[bytes] = []
        #: axis -> position counts (offset encoding), motion mode, running
        self.position = {1: 0x800000, 2: 0x800000}
        self.mode = {1: 0, 2: 0}
        self.running = {1: False, 2: False}
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def _loop(self) -> None:
        while True:
            try:
                data, peer = self.sock.recvfrom(1024)
            except OSError:
                return
            self.received.append(data)
            self.sock.sendto(self.reply(data) + CR, peer)

    def reply(self, data: bytes) -> bytes:
        cmd = data[1:2].decode()
        axis = int(data[2:3].decode())
        if data == b":F3" + CR:
            return b"="
        table = {
            "e": LIVE_VERSION,
            "a": LIVE_STEPS,
            "s": LIVE_TIMER,
        }
        if cmd in table:
            return b"=" + table[cmd].encode()
        if cmd == "j":
            return b"=" + encode_value(self.position[axis]).encode()
        if cmd == "f":
            # word layout per FINDINGS: digit1 B0 tracking B1 ccw B2 fast,
            # digit2 B0 running, digit3 B0 = NOT init done
            flags = 0
            if self.mode[axis] & 0x10:
                flags |= 0x100
            if self.mode[axis] & 0x01:
                flags |= 0x200
            if self.mode[axis] & 0x20:
                flags |= 0x400
            if self.running[axis]:
                flags |= 0x010
            return b"=" + format(flags, "03X").encode()
        writes = {"E", "G", "I", "S", "H", "M", "O", "J", "K", "L", "F"}
        if cmd in writes:
            if cmd == "E":
                self.position[axis] = int(decode_value(data[3:-1]))
            elif cmd == "G":
                self.mode[axis] = int(data[3:-1].decode(), 16)
            elif cmd == "J":
                self.running[axis] = True
            elif cmd in ("K", "L"):
                self.running[axis] = False
            return b"="
        return b"!0"

    def commands(self) -> list[str]:
        """Logged frames as ':Xn...' strings without trailing CR."""
        return [f.decode().rstrip("\r") for f in self.received]

    def close(self) -> None:
        self.sock.close()
        self._thread.join(timeout=1.0)


@pytest.fixture()
def sim() -> Iterator[MountSim]:
    sim = MountSim()
    yield sim
    sim.close()


def test_snapshot_against_simulator(sim: MountSim) -> None:
    client = SynscanClient(host="127.0.0.1", port=sim.addr[1], timeout=2.0)
    snap = client.snapshot()
    assert sim.received[0] == b":f1" + CR  # snapshot polls axes first
    assert snap.initialized is True
    assert snap.version == decode_value(LIVE_VERSION.encode())
    assert snap.steps_per_rev == 0x1FA400
    assert snap.timer_freq == 0x3840
    az, alt = snap.axes
    assert az.position_counts == 0  # 0x800000 - offset
    assert az.status_word == "000"  # no mode set in fresh sim
    assert az.init_done and not az.running
    assert alt.status_word == "000"
    # :F3, :j and :f frames all carry the CR terminator and no '#'
    assert all(msg.endswith(CR) and b"#" not in msg for msg in sim.received)


def test_simulator_rejects_garbage_like_real_mount(sim: MountSim) -> None:
    client = SynscanClient(host="127.0.0.1", port=sim.addr[1], timeout=2.0)
    with pytest.raises(SynscanCommandError) as excinfo:
        client.transact("z", AXIS_AZ)
    assert excinfo.value.code == 0  # unknown command
    assert sim.received[-1] == b":z1" + CR


def test_motion_gate_blocks_high_level_api(sim: MountSim) -> None:
    client = SynscanClient(host="127.0.0.1", port=sim.addr[1], timeout=2.0)
    for call in (
        lambda: client.slew(AXIS_AZ, 2.0),
        lambda: client.goto_degrees(AXIS_AZ, 180.0),
        lambda: client.sync_degrees(10.0, 20.0),
        lambda: client.initialize_axis(AXIS_ALT),
    ):
        with pytest.raises(MotionDeniedError):
            call()
    # sync_degrees calibrates lazily (read-only :a/:s may leak through),
    # but not a single write frame may leave the client
    write_cmds = {c[1] for c in sim.commands() if len(c) >= 2}
    assert write_cmds <= {"a", "s"}, sim.commands()


def test_slew_sequence_and_smooth_speed_change(sim: MountSim) -> None:
    client = SynscanClient(host="127.0.0.1", port=sim.addr[1], timeout=2.0, allow_motion=True)
    client.slew(AXIS_AZ, 2.0)
    # fresh axis: one status poll (:f+:j), track mode, lazy calibration,
    # period (14400/(2 deg/s * 5760 c/deg) = 1.25 -> quantised to 1), start
    assert sim.commands() == [
        ":f1",
        ":j1",
        ":G110",
        ":a1",
        ":s1",
        ":I1" + encode_value(1),
        ":J1",
    ]
    # same direction speed change: status poll + :I only, no stop/:G/:J hop
    client.slew(AXIS_AZ, 1.0)  # 14400/5760 = 2.5 -> 2
    assert sim.commands()[7:] == [":f1", ":j1", ":I1" + encode_value(2)]


def test_slew_direction_switch_stops_first(sim: MountSim) -> None:
    client = SynscanClient(host="127.0.0.1", port=sim.addr[1], timeout=2.0, allow_motion=True)
    client.slew(AXIS_AZ, 2.0)
    client.slew(AXIS_AZ, -2.0)  # reverse
    cmds = sim.commands()[7:]
    assert cmds[0] == ":f1"
    assert cmds[2] == ":K1"  # soft stop before switching direction
    assert ":G111" in cmds  # track CCW (0x10|0x01)
    assert cmds[-1] == ":J1"


def test_slew_zero_stops(sim: MountSim) -> None:
    client = SynscanClient(host="127.0.0.1", port=sim.addr[1], timeout=2.0, allow_motion=True)
    client.slew(AXIS_AZ, 0.0)
    assert sim.commands() == [":K1"]


def test_goto_degrees_sequence(sim: MountSim) -> None:
    client = SynscanClient(host="127.0.0.1", port=sim.addr[1], timeout=2.0, allow_motion=True)
    client.goto_degrees(AXIS_AZ, 90.0)
    cmds = sim.commands()
    assert cmds[0] == ":K1"
    assert cmds[1] == ":j1"  # current position for direction decision
    assert cmds[2:4] == [":a1", ":s1"]  # lazy calibration
    assert cmds[4] == ":G100"  # goto fast CW (mode 0x00)
    # :S uses the same 0x800000 offset as :E/:j (pysynscan motors.py:305)
    assert cmds[5] == ":S1" + encode_value(0x800000 + round(2073600 * 90.0 / 360.0))
    assert cmds[6] == ":J1"


def test_sync_and_read_degrees(sim: MountSim) -> None:
    client = SynscanClient(host="127.0.0.1", port=sim.addr[1], timeout=2.0, allow_motion=True)
    client.sync_degrees(10.0, 20.0)
    assert sim.commands() == [
        ":a1",
        ":s1",
        ":E1" + encode_value(0x800000 + round(2073600 * 10.0 / 360.0)),
        ":E2" + encode_value(0x800000 + round(2073600 * 20.0 / 360.0)),
    ]
    assert client.position_degrees(AXIS_AZ) == pytest.approx(10.0, abs=1e-3)
    assert client.position_degrees(AXIS_ALT) == pytest.approx(20.0, abs=1e-3)


def test_initialize_axis_sends_axis_init(sim: MountSim) -> None:
    client = SynscanClient(host="127.0.0.1", port=sim.addr[1], timeout=2.0, allow_motion=True)
    client.initialize_axis(AXIS_ALT)
    assert sim.commands() == [":F2"]


def test_set_switch_and_breakstep(sim: MountSim) -> None:
    client = SynscanClient(host="127.0.0.1", port=sim.addr[1], timeout=2.0, allow_motion=True)
    client.set_breakstep(AXIS_AZ, 0x0DAC)
    client.set_switch(False)
    assert sim.commands() == [":M1" + encode_value(0x0DAC), ":O10"]
