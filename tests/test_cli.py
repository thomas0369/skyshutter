from __future__ import annotations

import json
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
    camera_address: tuple[str, int],
    camera_server: SimulatorServer,
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(_args(camera_address, "shoot", "-n", "3", "--af")) == 0
    assert camera_server.captures == 6  # three autofocus drives, three exposures
    assert "exposure 3/3 triggered" in capsys.readouterr().out


def test_download_fetches_the_newest_captures(
    camera_address: tuple[str, int],
    camera_server: SimulatorServer,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    assert main(_args(camera_address, "shoot", "-n", "2")) == 0
    assert main(_args(camera_address, "download", "--last", "2", "-o", str(tmp_path))) == 0
    out = capsys.readouterr().out
    assert "MB ->" in out
    jpgs = sorted(tmp_path.glob("DSC_*.JPG"))
    assert len(jpgs) == 2
    assert jpgs[0].read_bytes()[:2] == b"\xff\xd8"


def test_download_list_shows_objects_without_fetching(
    camera_address: tuple[str, int],
    camera_server: SimulatorServer,
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(_args(camera_address, "shoot", "-n", "1")) == 0
    assert main(_args(camera_address, "download", "--list")) == 0
    assert "DSC_" in capsys.readouterr().out


def test_set_writes_exposure_settings(
    camera_address: tuple[str, int],
    camera_server: SimulatorServer,
) -> None:
    import struct as _s

    from skyshutter.nikon import DriveMode, ExposureProgram, NikonProperty, StandardProperty

    assert main(_args(camera_address, "set", "shutter", "1/30")) == 0
    assert main(_args(camera_address, "set", "iso", "800")) == 0
    assert main(_args(camera_address, "set", "aperture", "5.6")) == 0
    assert main(_args(camera_address, "set", "ev", "-0.7")) == 0
    assert main(_args(camera_address, "set", "program", "M")) == 0
    assert main(_args(camera_address, "set", "drive", "burst")) == 0
    assert camera_server.properties[NikonProperty.SHUTTER_SPEED] == _s.pack("<I", (1 << 16) | 30)
    assert camera_server.properties[StandardProperty.ISO] == _s.pack("<H", 800)
    assert camera_server.properties[StandardProperty.F_NUMBER] == _s.pack("<H", 560)
    assert camera_server.properties[StandardProperty.EXPOSURE_BIAS] == _s.pack("<h", -666)
    assert camera_server.properties[StandardProperty.EXPOSURE_PROGRAM] == _s.pack(
        "<H", int(ExposureProgram.MANUAL)
    )
    assert camera_server.properties[StandardProperty.STILL_CAPTURE_MODE] == _s.pack(
        "<H", int(DriveMode.BURST)
    )


def test_props_dump_then_diff_shows_changed_property(
    camera_address: tuple[str, int],
    camera_server: SimulatorServer,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    before = tmp_path / "before.json"
    after = tmp_path / "after.json"
    assert main(_args(camera_address, "props", "--dump", str(before))) == 0
    assert main(_args(camera_address, "set", "iso", "1600")) == 0
    assert main(_args(camera_address, "props", "--dump", str(after))) == 0

    dump = json.loads(before.read_text())
    assert "properties" in dump and "storage" in dump

    # The diff runs offline -- no camera -- and names exactly the change.
    rc = main(["props", "--diff", str(before), str(after)])
    out = capsys.readouterr().out
    assert rc == 0
    assert "0x500F" in out and "current" in out


def test_props_diff_without_changes_says_so(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    one = tmp_path / "one.json"
    two = tmp_path / "two.json"
    payload = {"properties": {"0xD100": {"current": 24, "default": 24}}}
    one.write_text(json.dumps(payload))
    two.write_text(json.dumps(payload))
    assert main(["props", "--diff", str(one), str(two)]) == 0
    assert "no property changes" in capsys.readouterr().out


def test_shoot_get_downloads_only_new_images(
    camera_address: tuple[str, int],
    camera_server: SimulatorServer,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    # One image exists already; --get must fetch only the fresh one.
    assert main(_args(camera_address, "shoot", "-n", "1")) == 0
    assert main(_args(camera_address, "shoot", "-n", "1", "--get", "-o", str(tmp_path))) == 0
    capsys.readouterr()
    files = list(tmp_path.glob("DSC_*.JPG"))
    assert len(files) == 1


def test_download_preview_fetches_smaller_object(
    camera_address: tuple[str, int],
    camera_server: SimulatorServer,
    tmp_path: Path,
) -> None:
    assert main(_args(camera_address, "shoot", "-n", "1")) == 0
    assert (
        main(_args(camera_address, "download", "--last", "1", "--preview", "-o", str(tmp_path)))
        == 0
    )
    previews = list(tmp_path.glob("*_preview.jpg"))
    assert len(previews) == 1
    data = previews[0].read_bytes()
    assert data[:2] == b"\xff\xd8" and data[-2:] == b"\xff\xd9"
    # The preview must be genuinely smaller than the stored full frame.
    full = next(iter(camera_server.objects.values()))
    assert len(data) < len(full)


def test_bundle_collects_everything_in_one_directory(
    camera_address: tuple[str, int],
    camera_server: SimulatorServer,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    out = tmp_path / "b"
    assert main(_args(camera_address, "bundle", "-o", str(out))) == 0
    assert "bundle ->" in capsys.readouterr().out
    info = json.loads((out / "device-info.json").read_text())
    assert "COOLPIX" in info["model"]
    props = json.loads((out / "props.json").read_text())
    assert props
    # Every entry carries either a parsed descriptor or a recorded failure;
    # descriptors additionally keep the raw bytes for offline diagnosis.
    for entry in props.values():
        assert "desc" in entry or "fetch_error" in entry
        if "desc" in entry:
            assert "raw" in entry
    json.loads((out / "events.json").read_text())
    frame = (out / "frame.jpg").read_bytes()
    assert frame[:2] == b"\xff\xd8"


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
    # 0x90C7 (old event poll) is not offered by this camera, so the simulator
    # answers OPERATION_NOT_SUPPORTED, as the real camera would.
    assert main(_args(camera_address, "raw", "0x90C7")) == 1
    assert "OPERATION_NOT_SUPPORTED" in capsys.readouterr().out


def test_raw_rejects_too_many_params_gracefully(
    camera_address: tuple[str, int], capsys: pytest.CaptureFixture[str]
) -> None:
    # PTP only allows 5 params, providing 6 should throw ValueError and exit 1
    assert main(_args(camera_address, "raw", "0x1001", "1", "2", "3", "4", "5", "6")) == 1
    assert "PTP allows at most 5 operation parameters" in capsys.readouterr().err


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


def _synthetic_pairing_json(tmp_path: Path) -> Path:
    """A pairing JSON built from made-up numbers -- no real device data."""
    import json

    from skyshutter import lssec

    own_ts = bytes.fromhex("1122334455667788")
    camera_ts = bytes.fromhex("99aabbccddeeff00")
    device_id = bytes.fromhex("0102030405060708")
    stage4_payload = bytes.fromhex("4142434445464748")
    salt_index = 5
    challenge = lssec._mac(lssec._SALTS[salt_index] + camera_ts + own_ts)
    key = lssec.session_key(stage4_payload, device_id, own_ts, camera_ts, challenge)
    bf = lssec._Blowfish(key)
    zero = bytes(8)
    ssid = b"NIGHTCAM_TEST".ljust(32, b"\x00")
    password = b"hunter2secret".ljust(64, b"\x00")
    config = bytes([0x03]) + bf.encrypt_cbc(ssid, zero) + bf.encrypt_cbc(password, zero) + b"\x03"

    doc = {
        "stage1": (b"\x01" + own_ts + device_id).hex(),
        "stage2": (b"\x02" + camera_ts + challenge).hex(),
        "stage4": (b"\x04" + bytes(8) + stage4_payload).hex(),
        "config": config.hex(),
    }
    path = tmp_path / "pairing.json"
    path.write_text(json.dumps(doc))
    return path


def test_wifi_decrypts_from_a_pairing_json(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = _synthetic_pairing_json(tmp_path)
    assert main(["wifi", str(path)]) == 0
    out = capsys.readouterr().out
    assert "NIGHTCAM_TEST" in out
    assert "hunter2secret" in out


def test_wifi_connect_prints_an_nmcli_line(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = _synthetic_pairing_json(tmp_path)
    assert main(["wifi", str(path), "--connect"]) == 0
    out = capsys.readouterr().out
    assert "nmcli device wifi connect" in out
    assert "NIGHTCAM_TEST" in out


def test_wifi_without_values_explains_what_is_missing(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(["wifi"]) == 1
    assert "missing" in capsys.readouterr().err
