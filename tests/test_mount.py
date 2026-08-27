"""Tests for the SynScan mount client (protocol core, gate, loopback sim)."""

from __future__ import annotations

import socket
import threading
from collections.abc import Iterator

import pytest

from skyshutter.mount import (
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
LIVE_STEPS = "00A41F"  # 0x1FA400 = 2073088 steps/rev
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
    """Minimal UDP echo server imitating the AZ-GTi (read commands only)."""

    def __init__(self) -> None:
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(("127.0.0.1", 0))
        self.sock.settimeout(2.0)
        self.addr = self.sock.getsockname()
        self.received: list[bytes] = []
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
        axis = data[2:3].decode()
        if data == b":F3" + CR:
            return b"="
        table = {
            "e": LIVE_VERSION,
            "a": LIVE_STEPS,
            "s": LIVE_TIMER,
            "j": LIVE_J,
        }
        if cmd in table:
            return b"=" + table[cmd].encode()
        if cmd == "f":
            return b"=" + LIVE_F[int(axis) - 1].encode()
        return b"!0"

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
    assert az.status_word == "100"
    assert az.init_done and not az.running
    assert alt.status_word == "101"
    # :F3, :j and :f frames all carry the CR terminator and no '#'
    assert all(msg.endswith(CR) and b"#" not in msg for msg in sim.received)


def test_simulator_rejects_garbage_like_real_mount(sim: MountSim) -> None:
    client = SynscanClient(host="127.0.0.1", port=sim.addr[1], timeout=2.0)
    with pytest.raises(SynscanCommandError) as excinfo:
        client.transact("z", AXIS_AZ)
    assert excinfo.value.code == 0  # unknown command
    assert sim.received[-1] == b":z1" + CR
