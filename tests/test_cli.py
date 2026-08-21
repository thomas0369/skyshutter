from __future__ import annotations

from pathlib import Path

import pytest

from skyshutter.cli import main
from skyshutter.simulator import SimulatorServer

GUID = "11111111-2222-3333-4444-555555555555"


@pytest.fixture(autouse=True)
def stable_identity(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep the tests away from the user's real config file."""
    monkeypatch.setenv("SKYSHUTTER_GUID", GUID)
    monkeypatch.setenv("SKYSHUTTER_NAME", "pytest")


def _args(camera_address: tuple[str, int], *rest: str) -> list[str]:
    host, port = camera_address
    return ["--host", host, "--port", str(port), *rest]


def test_probe_reports_the_open_ptpip_port(
    camera_address: tuple[str, int], capsys: pytest.CaptureFixture[str]
) -> None:
    _, port = camera_address
    assert main(_args(camera_address, "probe", "--ports", str(port))) == 0
    out = capsys.readouterr().out
    assert f"open  {port:>6}" in out
    assert "PTP/IP handshake OK" in out
    assert "COOLPIX P1100" in out


def test_probe_without_a_camera(capsys: pytest.CaptureFixture[str]) -> None:
    # Port 1 is closed on the loopback interface.
    assert main(["--host", "127.0.0.1", "--port", "1", "probe", "--ports", "1"]) == 1
    assert "nothing reachable" in capsys.readouterr().out


def test_info_lists_supported_operations(
    camera_address: tuple[str, int], capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(_args(camera_address, "info")) == 0
    out = capsys.readouterr().out
    assert "COOLPIX P1100" in out
    assert "Nikon Corporation" in out
    assert "0x9203  GET_LIVE_VIEW_IMG" in out
    assert "0x1002  OPEN_SESSION" in out


def test_shoot_triggers_the_requested_number_of_exposures(
    camera_address: tuple[str, int], camera_server: SimulatorServer,
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(_args(camera_address, "shoot", "-n", "3", "--af")) == 0
    assert camera_server.captures == 6  # three autofocus drives, three exposures
    assert "exposure 3/3 triggered" in capsys.readouterr().out


def test_liveview_writes_frames_to_disk(
    camera_address: tuple[str, int], tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    out_dir = tmp_path / "frames"
    assert main(_args(camera_address, "liveview", "-o", str(out_dir), "-n", "2", "--fps", "0")) == 0
    written = sorted(out_dir.glob("*.jpg"))
    assert len(written) == 2
    assert written[0].read_bytes().startswith(b"\xff\xd8\xff")
    assert str(out_dir) in capsys.readouterr().out


def test_raw_prints_the_response_and_data(
    camera_address: tuple[str, int], capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(_args(camera_address, "raw", "0x1001")) == 0
    out = capsys.readouterr().out
    assert "response OK [0x2001]" in out
    assert "data " in out


def test_raw_reports_an_unsupported_opcode(
    camera_address: tuple[str, int], capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(_args(camera_address, "raw", "0x90CA")) == 1
    assert "OPERATION_NOT_SUPPORTED" in capsys.readouterr().out


def test_raw_can_dump_the_data_phase_to_a_file(
    camera_address: tuple[str, int], tmp_path: Path
) -> None:
    target = tmp_path / "deviceinfo.bin"
    assert main(_args(camera_address, "raw", "0x1001", "-o", str(target))) == 0
    assert target.stat().st_size > 0


def test_network_errors_are_reported_without_a_traceback(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(["--host", "127.0.0.1", "--port", "1", "info"]) == 1
    assert "error" in capsys.readouterr().err


def test_connection_options_work_before_and_after_the_subcommand(
    camera_address: tuple[str, int], capsys: pytest.CaptureFixture[str]
) -> None:
    host, port = camera_address
    before = ["--host", host, "--port", str(port), "probe", "--ports", str(port)]
    after = ["probe", "--host", host, "--port", str(port), "--ports", str(port)]
    assert main(before) == 0
    first = capsys.readouterr().out
    assert main(after) == 0
    assert capsys.readouterr().out == first


def test_verbose_flag_is_kept_when_given_before_the_subcommand(
    camera_address: tuple[str, int],
) -> None:
    from skyshutter.cli import build_parser

    args = build_parser().parse_args(["-vv", "probe"])
    assert args.verbose == 2
    assert build_parser().parse_args(["probe", "-v"]).verbose == 1
    assert not hasattr(build_parser().parse_args(["probe"]), "verbose")
