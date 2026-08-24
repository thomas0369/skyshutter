"""ble-watch status: the file every gating decision reads.

The -127 lesson (24.08. evening): -127 is the HCI "not available" marker,
not a field strength, and a sighting's identity is only provable via the
name field (the camera rotates its LE address). Status output must show
both correctly -- run blocks have aborted or misdiagnosed on either.
"""

import importlib.util
import json
import os
import time


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "ble_watch",
        os.path.join(os.path.dirname(__file__), "..", "tools", "ble-watch.py"),
    )
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _write_status(tmp_path, payload):
    status = tmp_path / "camera_seen.json"
    status.write_text(json.dumps(payload))
    return str(status)


def test_status_shows_na_for_hci_marker_and_the_name(tmp_path, monkeypatch, capsys):
    mod = _load_module()
    monkeypatch.setenv(
        "SKYSHUTTER_CAM_STATUS",
        _write_status(
            tmp_path,
            {
                "ts": time.time() - 1.0,
                "addr": "51:D6:74:D3:55:5A",
                "name": "P1100_<serno>",
                "rssi": -127,
                "flags": {},
            },
        ),
    )
    mod.STATUS_FILE = os.environ["SKYSHUTTER_CAM_STATUS"]
    rc = mod.run_status()
    out = capsys.readouterr().out
    assert rc == 0  # fresh sighting
    assert "rssi=n/a" in out  # -127 is not a signal strength
    assert "P1100_<serno>" in out  # identity via name, address rotates


def test_status_exit_codes_fresh_stale_never(tmp_path, monkeypatch):
    mod = _load_module()
    fresh = _write_status(tmp_path, {"ts": time.time() - 2.0, "rssi": -70})
    monkeypatch.setenv("SKYSHUTTER_CAM_STATUS", fresh)
    mod.STATUS_FILE = fresh
    assert mod.run_status() == 0

    stale = _write_status(tmp_path, {"ts": time.time() - 120.0, "rssi": -70})
    monkeypatch.setenv("SKYSHUTTER_CAM_STATUS", stale)
    mod.STATUS_FILE = stale
    assert mod.run_status() == 2

    monkeypatch.setenv("SKYSHUTTER_CAM_STATUS", str(tmp_path / "does-not-exist.json"))
    mod.STATUS_FILE = str(tmp_path / "does-not-exist.json")
    assert mod.run_status() == 3
