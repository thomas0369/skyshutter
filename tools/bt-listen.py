#!/usr/bin/env python3
"""Passive Bluetooth radar -- hear everything, transmit nothing.

The pairing battles of 23./24.08. raised a hypothesis: our own radio traffic
(scan requests, inquiries, pairing attempts) may be what pushes the camera
into its refusal state (pairing.md Falle 5a -- only hours of radio silence
helped). This service is the opposite of every tool before it: the adapter
runs in PASSIVE scan mode (HCI scan_type 0x00 -- it never transmits a single
bit) and everything the radio receives is decoded and logged:

  * every LE advertisement: address, type (ADV_IND / NONCONN / ...), RSSI,
    name, service UUIDs, manufacturer data
  * Nikon manufacturer payload (company 0x0399): the LSS ad-info byte
    (quickWakeUp / autoTransfer / btcCoopWait + the unexplained bit0)
  * classic connection attempts aimed at us (Connection Request events)

Outputs on the machine it runs on:
  /tmp/bt-radar.jsonl     every logged event, one JSON per line
  /tmp/camera_seen.json   compatibility status file (same shape ble-watch
                          wrote; remote-start --wait-for-ad keeps working)
  stdout (journald)       Nikon sightings, new devices, heartbeat

Runs as a ROOT systemd service (raw HCI socket needs CAP_NET_RAW).

Passive mode measures one open question by itself: if the Nikon manufacturer
data still arrives without scan requests, readiness detection needs zero
transmitting; if not, we know the LSS byte only rides in scan responses.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import socket
import struct
import sys
import tempfile
import time

HCI_EVENT_PKT = 0x04
EVT_CONN_REQUEST = 0x04
EVT_CMD_COMPLETE = 0x0E
EVT_CMD_STATUS = 0x0F
EVT_LE_META = 0x3E
LE_ADV_REPORT = 0x02

OGF_LE = 0x08
OCF_LE_SET_SCAN_PARAMS = 0x000B
OCF_LE_SET_SCAN_ENABLE = 0x000C
SCAN_PARAMS_OPCODE = (OGF_LE << 10) | OCF_LE_SET_SCAN_PARAMS
SCAN_ENABLE_OPCODE = (OGF_LE << 10) | OCF_LE_SET_SCAN_ENABLE

SCAN_INTERVAL = 0x0030
SCAN_WINDOW = 0x0030

NIKON_COMPANY = 0x0399
NIKON_SERVICE = "0000de00-3dd4-4255-8d62-6dc7b9bd5561"

EVT_TYPE_NAMES = {
    0x00: "ADV_IND",
    0x01: "ADV_DIRECT_IND",
    0x02: "SCAN_RSP",
    0x03: "ADV_SCAN_IND",
    0x04: "ADV_NONCONN_IND",
}

AD_TYPE_NAMES = {
    0x01: "flags",
    0x02: "uuids16-incomplete",
    0x03: "uuids16",
    0x06: "uuids128-incomplete",
    0x07: "uuids128",
    0x08: "name-short",
    0x09: "name",
    0x0A: "tx-power",
    0x16: "service-data",
    0xFF: "manufacturer",
}

CAMERA_SEEN = os.environ.get("SKYSHUTTER_CAM_STATUS", "/tmp/camera_seen.json")
RADAR_JSONL = os.environ.get("SKYSHUTTER_RADAR_LOG", "/tmp/bt-radar.jsonl")
NIKON_LOG_EVERY = 2.0
OTHER_LOG_EVERY = 120.0
HEARTBEAT = 300.0


def decode_flags(manufacturer: bytes | None) -> dict:
    """LSS ad-info byte is payload[4]; measured 23.08., FINDINGS."""
    if not manufacturer or len(manufacturer) < 5:
        return {}
    b = manufacturer[4]
    return {
        "quickWakeUp": bool(b & 0x08),
        "autoTransfer": bool(b & 0x02),
        "btcCoopWait": bool(b & 0x10),
        "bit0_unbekannt": bool(b & 0x01),
        "raw": f"0x{b:02x}",
    }


def parse_ad(data: bytes) -> dict:
    """Split advertising data into its structures (pure, unit-tested)."""
    out = {"names": [], "uuids": [], "mfg": {}, "tx_power": None, "raw_len": len(data)}
    off = 0
    while off < len(data):
        if off + 1 >= len(data):
            break
        ln = data[off]
        if ln == 0 or off + 1 + ln > len(data):
            break
        ad_type = data[off + 1]
        payload = data[off + 2 : off + 1 + ln]
        if ad_type in (0x08, 0x09):
            try:
                out["names"].append(payload.decode("utf-8", "replace"))
            except Exception:
                pass
        elif ad_type in (0x02, 0x03):
            for i in range(0, len(payload) - 1, 2):
                u = struct.unpack("<H", payload[i : i + 2])[0]
                out["uuids"].append(f"{u:04x}")
        elif ad_type in (0x06, 0x07):
            for i in range(0, len(payload) - 15, 16):
                h = payload[i : i + 16][::-1].hex()
                out["uuids"].append(f"{h[0:8]}-{h[8:12]}-{h[12:16]}-{h[16:20]}-{h[20:32]}")
        elif ad_type == 0x0A and payload:
            out["tx_power"] = struct.unpack("b", payload[:1])[0]
        elif ad_type == 0xFF and len(payload) >= 2:
            company = struct.unpack("<H", payload[:2])[0]
            out["mfg"][company] = payload[2:].hex()
        off += 1 + ln
    return out


def parse_adv_report(data: bytes) -> list[dict]:
    """Parse one LE Advertising Report meta event into reports (pure)."""
    reports = []
    if not data or data[0] != LE_ADV_REPORT:
        return reports
    num = data[1]
    off = 2
    for _ in range(num):
        if off + 9 > len(data):
            break
        evt_type = data[off]
        addr_type = data[off + 1]
        addr = ":".join(f"{b:02X}" for b in reversed(data[off + 2 : off + 8]))
        adv_len = data[off + 8]
        if off + 9 + adv_len + 1 > len(data):
            break
        adv = data[off + 9 : off + 9 + adv_len]
        rssi = struct.unpack("b", data[off + 9 + adv_len : off + 10 + adv_len])[0]
        reports.append(
            {
                "evt_type": evt_type,
                "evt_name": EVT_TYPE_NAMES.get(evt_type, f"0x{evt_type:02x}"),
                "addr_type": "public" if addr_type == 0 else "random",
                "addr": addr,
                "rssi": rssi,
                "ad": adv,
            }
        )
        off += 10 + adv_len
    return reports


def is_nikon(parsed: dict) -> bool:
    if NIKON_COMPANY in parsed["mfg"]:
        return True
    if any(n and n.startswith("P110") for n in parsed["names"]):
        return True
    return any(u.lower() == NIKON_SERVICE for u in parsed["uuids"])


def write_camera_status(payload: dict) -> None:
    d = os.path.dirname(CAMERA_SEEN) or "/tmp"
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".camseen_")
    try:
        with os.fdopen(fd, "w") as fh:
            json.dump(payload, fh)
        os.replace(tmp, CAMERA_SEEN)
    except OSError:
        try:
            os.unlink(tmp)
        except OSError:
            pass


def hci_command(sock: socket.socket, opcode: int, params: bytes) -> None:
    sock.send(struct.pack("<BHB", 0x01, opcode, len(params)) + params)


def start_passive_scan(sock: socket.socket) -> None:
    params = struct.pack("<BHHBB", 0x00, SCAN_INTERVAL, SCAN_WINDOW, 0x00, 0x00)
    hci_command(sock, SCAN_PARAMS_OPCODE, params)
    hci_command(sock, SCAN_ENABLE_OPCODE, struct.pack("<BB", 0x01, 0x00))


def cmd_status_name(status: int) -> str:
    names = {
        0x00: "SUCCESS",
        0x01: "UNKNOWN_CMD",
        0x0C: "CMD_DISALLOWED",
        0x11: "UNSUPPORTED",
        0x12: "INVALID_PARAMS",
        0x22: "CMD_PENDING",
    }
    return names.get(status, f"0x{status:02x}")


def wait_cmd_complete(sock: socket.socket, opcode: int, timeout: float = 3.0) -> int | None:
    """Read events until the Command Complete for opcode arrives (or timeout)."""
    deadline = time.monotonic() + timeout
    sock.settimeout(max(0.1, deadline - time.monotonic()))
    while time.monotonic() < deadline:
        try:
            pkt = sock.recv(4096)
        except (socket.timeout, OSError):
            break
        if not pkt or pkt[0] != HCI_EVENT_PKT:
            continue
        if pkt[1] == EVT_CMD_STATUS and len(pkt) >= 7:
            rcv_op = struct.unpack("<H", pkt[4:6])[0]
            if rcv_op == opcode:
                return pkt[3]
        if pkt[1] == EVT_CMD_COMPLETE and len(pkt) >= 7:
            rcv_op = struct.unpack("<H", pkt[4:6])[0]
            if rcv_op == opcode:
                return pkt[7]
    return None


def stop_scan(sock: socket.socket) -> None:
    try:
        hci_command(sock, SCAN_ENABLE_OPCODE, struct.pack("<BB", 0x00, 0x00))
    except OSError:
        pass


def open_hci_user_channel(dev: int) -> socket.socket:
    """Bind the exclusive HCI USER channel.

    The kernel vetoes raw scan commands while BlueZ owns the adapter via mgmt
    (measured: 'Set scan parameters failed: Operation not permitted', for
    hcitool and for us alike). The USER channel bypasses kernel and BlueZ
    entirely -- requirement: bluetooth.service must be stopped. As a side
    effect NOTHING else can use the radio while the radar runs: the strongest
    possible form of "send nothing".
    """
    sock = socket.socket(socket.AF_BLUETOOTH, socket.SOCK_RAW, socket.BTPROTO_HCI)
    try:
        sock.bind((dev, 1))  # 1 = HCI_CHANNEL_USER
    except (OSError, TypeError) as exc:
        sock.close()
        print(
            f"radar: USER-Kanal fuer hci{dev} nicht verfuegbar ({exc}).\n"
            "  Bluetooth-Dienst stoppen: sudo systemctl stop bluetooth",
            file=sys.stderr,
        )
        raise SystemExit(2) from exc
    return sock


def main() -> int:
    p = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    p.add_argument("--device", type=int, default=0, help="HCI device index")
    args = p.parse_args()

    try:
        sock = open_hci_user_channel(args.device)
    except PermissionError as exc:
        print(f"radar: kein Zugriff auf hci{args.device}: {exc}", file=sys.stderr)
        return 1

    last_sig: dict[tuple, float] = {}
    events = 0
    devices: dict[str, dict] = {}
    started = time.monotonic()
    last_beat = time.monotonic()

    try:
        start_passive_scan(sock)
        for label, opcode in (
            ("scan-params", SCAN_PARAMS_OPCODE),
            ("scan-enable", SCAN_ENABLE_OPCODE),
        ):
            st = wait_cmd_complete(sock, opcode)
            print(
                f"{time.strftime('%H:%M:%S')}  {label}: "
                f"{cmd_status_name(st) if st is not None else 'keine Antwort'}",
                flush=True,
            )
        sock.settimeout(None)
        print(
            f"{time.strftime('%H:%M:%S')}  radar aktiv (PASSIV, sendet nichts) "
            f"auf hci{args.device}",
            flush=True,
        )
        while True:
            pkt = sock.recv(4096)
            if not pkt or pkt[0] != HCI_EVENT_PKT:
                continue
            evt = pkt[1]
            payload = pkt[3:]
            if evt == EVT_LE_META:
                for rep in parse_adv_report(payload):
                    events += 1
                    parsed = parse_ad(rep["ad"])
                    addr = rep["addr"]
                    dev = devices.setdefault(addr, {"first": time.time(), "events": 0})
                    dev["events"] += 1
                    mfg_hex = parsed["mfg"].get(NIKON_COMPANY)
                    nikon = is_nikon(parsed)
                    entry = {
                        "ts": round(time.time(), 3),
                        "addr": addr,
                        "addr_type": rep["addr_type"],
                        "evt": rep["evt_name"],
                        "rssi": rep["rssi"],
                        "names": parsed["names"],
                        "uuids": parsed["uuids"],
                        "mfg": {f"0x{c:04x}": h for c, h in parsed["mfg"].items()},
                        "nikon": nikon,
                    }
                    if nikon and mfg_hex:
                        entry["lss"] = decode_flags(bytes.fromhex(mfg_hex))
                    sig = (
                        addr,
                        rep["evt_type"],
                        hashlib.sha1(rep["ad"]).hexdigest()[:8],
                    )
                    now = time.monotonic()
                    interval = NIKON_LOG_EVERY if nikon else OTHER_LOG_EVERY
                    if now - last_sig.get(sig, 0) >= interval:
                        last_sig[sig] = now
                        try:
                            with open(RADAR_JSONL, "a") as fh:
                                fh.write(json.dumps(entry) + "\n")
                        except OSError:
                            pass
                        if nikon:
                            lss = entry.get("lss", {})
                            f = " ".join(f"{k}={v}" for k, v in lss.items() if k != "raw")
                            print(
                                f"{time.strftime('%H:%M:%S')}  NIKON {addr} "
                                f"{rep['evt_name']} rssi={rep['rssi']} "
                                f"mfg={mfg_hex or '-'} {f}",
                                flush=True,
                            )
                            write_camera_status(
                                {
                                    "ts": entry["ts"],
                                    "addr": addr,
                                    "rssi": rep["rssi"],
                                    "name": (parsed["names"] or [""])[0],
                                    "flags": lss,
                                }
                            )
                    elif nikon:
                        write_camera_status(
                            {
                                "ts": entry["ts"],
                                "addr": addr,
                                "rssi": rep["rssi"],
                                "name": (parsed["names"] or [""])[0],
                                "flags": entry.get("lss", {}),
                            }
                        )
            elif evt == EVT_CONN_REQUEST and len(payload) >= 11:
                addr = ":".join(f"{b:02X}" for b in reversed(payload[0:6]))
                cod = payload[6:9]
                print(
                    f"{time.strftime('%H:%M:%S')}  EINGEHENDE VERBINDUNG {addr} class={cod.hex()}",
                    flush=True,
                )
                try:
                    with open(RADAR_JSONL, "a") as fh:
                        fh.write(
                            json.dumps(
                                {
                                    "ts": time.time(),
                                    "event": "connection_request",
                                    "addr": addr,
                                    "class": cod.hex(),
                                }
                            )
                            + "\n"
                        )
                except OSError:
                    pass

            if time.monotonic() - last_beat >= HEARTBEAT:
                last_beat = time.monotonic()
                print(
                    f"{time.strftime('%H:%M:%S')}  heartbeat: {events} Ereignisse, "
                    f"{len(devices)} Geraete seit Start "
                    f"({time.monotonic() - started:.0f}s)",
                    flush=True,
                )
    except KeyboardInterrupt:
        pass
    finally:
        stop_scan(sock)
        sock.close()
        print(f"{time.strftime('%H:%M:%S')}  radar gestoppt", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
