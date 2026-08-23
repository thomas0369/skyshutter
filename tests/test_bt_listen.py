"""bt-listen: pure parser tests with a synthetic Nikon advertisement."""

import importlib.util
import os

spec = importlib.util.spec_from_file_location(
    "bt_listen",
    os.path.join(os.path.dirname(__file__), "..", "tools", "bt-listen.py"),
)
assert spec is not None and spec.loader is not None
bt_listen = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bt_listen)


def _ad(*structures: bytes) -> bytes:
    return b"".join(structures)


def test_parse_ad_extracts_name_uuid_and_manufacturer():
    name = b"\x05\x09P110"
    uuid16 = b"\x03\x03\x99\x03"
    mfg = b"\x0a\xff\x99\x03" + bytes.fromhex("01c96e6b0001")
    parsed = bt_listen.parse_ad(_ad(name, uuid16, mfg))
    assert parsed["names"] == ["P110"]
    assert "9903" in parsed["uuids"]
    assert parsed["mfg"] == {0x0399: "01c96e6b0001"}


def test_decode_flags_known_bits_and_raw():
    flags = bt_listen.decode_flags(bytes.fromhex("01c96e6b08"))
    assert flags["quickWakeUp"] is True
    assert flags["autoTransfer"] is False
    assert flags["raw"] == "0x08"
    flags2 = bt_listen.decode_flags(bytes.fromhex("01c96e6b01"))
    assert flags2["bit0_unbekannt"] is True


def test_decode_flags_short_payload_is_empty():
    assert bt_listen.decode_flags(b"\x99\x03") == {}
    assert bt_listen.decode_flags(None) == {}


def test_parse_adv_report_layout():
    adv = b"\x02\x01\x06" + b"\x05\x09P110"
    report = bytes([0x02, 0x01])  # subevent LE_ADV_REPORT, 1 report
    report += bytes([0x04])  # ADV_NONCONN_IND
    report += bytes([0x01])  # random address
    report += bytes([0x11, 0x22, 0x33, 0x44, 0x55, 0x66])  # LE order
    report += bytes([len(adv)]) + adv + struct_rssi(0xC6)  # -58
    reports = bt_listen.parse_adv_report(report)
    assert len(reports) == 1
    r = reports[0]
    assert r["addr"] == "66:55:44:33:22:11"
    assert r["evt_name"] == "ADV_NONCONN_IND"
    assert r["addr_type"] == "random"
    assert r["rssi"] == -58
    assert bt_listen.parse_ad(r["ad"])["names"] == ["P110"]


def struct_rssi(dbm: int) -> bytes:
    return bytes([dbm & 0xFF])


def test_parse_adv_report_truncated_is_safe():
    assert bt_listen.parse_adv_report(bytes([0x02, 0x01, 0x00, 0x00, 0x01])) == []
    assert bt_listen.parse_adv_report(b"") == []
    assert bt_listen.parse_adv_report(bytes([0x03])) == []


def test_is_nikon_detection_paths():
    by_mfg = {"names": [], "uuids": [], "mfg": {0x0399: "00"}}
    assert bt_listen.is_nikon(by_mfg)
    by_name = {"names": ["P1100_<serno>"], "uuids": [], "mfg": {}}
    assert bt_listen.is_nikon(by_name)
    other = {"names": ["LG TV"], "uuids": [], "mfg": {0x00E0: "00"}}
    assert not bt_listen.is_nikon(other)
