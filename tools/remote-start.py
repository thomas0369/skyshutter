#!/usr/bin/env python3
"""Start remote photography the way SnapBridge does -- BLE, then WiFi live view.

Built from docs/REMOTE_SEQUENCE.md, the sequence reconstructed from a working
SnapBridge btsnoop. It corrects two earlier mistakes: the camera is ready when
POWER_CONTROL reads 0x03 (VALID_WAKE, not INVALID_WAKE), and there is NO RFCOMM
data channel -- the only classic step is a bond. The BLE differences that our
earlier bare 0x2005 write skipped are the CCCD subscriptions (indicate 0x2000,
notify 0x2008) and doing the establishment inside one full, bonded session.

Stages (each prints, stops on hard failure):
  1. ensure a classic bond to the camera exists (bond = wake enabler)
  2. BLE connect (plain link), subscribe CCCDs, run the 4-stage LSS handshake
  3. read POWER_CONTROL, write client name, read + decrypt the 0x2004 creds
  4. write ESTABLISHMENT 0x2005 = 0x01 (WiFi) and hold the link
  5. scan for the camera's access point; with --join, join it and open PTP/IP
     live view (OpenSession -> StartLiveView 0x9201 -> one GetLiveViewImageEx)

    python tools/remote-start.py --register skyshutter --hold 60
    python tools/remote-start.py --register skyshutter --join      # also join + live view

Runs under Windows Python (bleak + winrt) or under Linux (bleak + BlueZ).
On Linux the classic bond is checked via bluetoothctl against the camera's
static BR/EDR address, and --join uses NetworkManager (nmcli) on wlan0.
Reuses nikon_pairing and, from the installed package, lssec / ptpip / nikon.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "src"))

try:
    from bleak import BleakClient, BleakScanner
except ImportError:  # pragma: no cover - bench tool
    sys.exit("bleak is missing: pip install bleak")

import nikon_pairing as np  # noqa: E402  (local, after sys.path insert)

try:
    from skyshutter import lssec
except ImportError:  # pragma: no cover
    lssec = None

VENDOR = "-3dd4-4255-8d62-6dc7b9bd5561"
SERVICE = f"0000de00{VENDOR}"
AUTH = f"00002000{VENDOR}"
POWER = f"00002001{VENDOR}"
NAME = f"00002002{VENDOR}"
CONFIG = f"00002004{VENDOR}"
ESTABLISH = f"00002005{VENDOR}"
CONTROL_POINT = f"00002008{VENDOR}"

# Wire values (field a / getByte), verified from BlePowerControlData$Types.smali.
POWER_TYPES = {
    0xFF: "UNDEFINED",
    0x00: "STOP",
    0x01: "WAKE_WAIT",
    0x02: "INVALID_WAKE",
    0x03: "VALID_WAKE",
}


def log(msg: str) -> None:
    print(f"{time.strftime('%H:%M:%S')}  {msg}", flush=True)


def hexs(data: bytes) -> str:
    return data.hex() if data else "(leer)"


# Static BR/EDR address of the camera (dual-mode device, separate from the LE
# RPA). The classic bond to THIS address is the wake enabler; measured 23.08.
CAMERA_CLASSIC_MAC = "7C:B8:DA:A6:4F:FE"

IS_WINDOWS = sys.platform == "win32"


async def ensure_bond(name_hint: str) -> None:
    """Stage 1: make sure a classic bond to the camera exists (the wake enabler)."""
    if not IS_WINDOWS:
        out = subprocess.run(
            ["bluetoothctl", "info", CAMERA_CLASSIC_MAC], capture_output=True, text=True, timeout=10
        ).stdout
        if "Paired: yes" in out:
            log(f"  classic bond vorhanden: {CAMERA_CLASSIC_MAC}")
            return
        log("  kein classic Bond -- einmalig ausfuehren (Kamera in Kopplungsbereitschaft):")
        log(
            f"    bluetoothctl: remove {CAMERA_CLASSIC_MAC}; pair {CAMERA_CLASSIC_MAC};"
            f" trust {CAMERA_CLASSIC_MAC}"
        )
        log("  (fahre trotzdem fort; die Kamera ignoriert 0x2005 evtl. ohne Bond)")
        return
    try:
        from winrt.windows.devices.bluetooth import BluetoothDevice
        from winrt.windows.devices.enumeration import DeviceInformation
    except ImportError:
        log("  (winrt fehlt -- Bond-Prüfung übersprungen; classic-pair.py separat sicherstellen)")
        return
    selector = BluetoothDevice.get_device_selector_from_pairing_state(True)
    found = await DeviceInformation.find_all_async_aqs_filter(selector)
    for i in range(found.size):
        info = found.get_at(i)
        if name_hint.lower() in (info.name or "").lower():
            log(f"  classic bond vorhanden: {info.name!r}")
            return
    log(f"  kein classic Bond zu {name_hint!r} -- bitte 'classic-pair.py pair' laufen lassen.")
    log("  (fahre trotzdem fort; die Kamera ignoriert 0x2005 evtl. ohne Bond)")


async def find_camera(timeout: float):
    def match(_dev, adv):
        return any(u.lower() == SERVICE for u in (adv.service_uuids or []))

    return await BleakScanner.find_device_by_filter(match, timeout=timeout)


async def wait_for_ad(timeout: float) -> bool:
    """Block until the ble-watch scanner service reports a FRESH sighting.

    The camera advertises in bursts; a one-shot scan hitting a silent phase
    was pure luck (playbook trap 6). The always-on scanner removes the luck:
    we wait for its status file, then the short find_camera is guaranteed to
    hit an active advertising phase.
    """
    import json

    deadline = time.monotonic() + timeout
    warned = False
    while time.monotonic() < deadline:
        try:
            with open(os.path.join(os.environ.get("TMPDIR", "/tmp"), "camera_seen.json")) as fh:
                data = json.load(fh)
            age = time.time() - data.get("ts", 0)
            if age < 10:
                flags = data.get("flags", {})
                f = ",".join(k for k, v in flags.items() if v is True) or "ruhend"
                log(f"  Scanner: Sichtung vor {age:.1f}s (rssi {data.get('rssi')}, {f})")
                return True
        except (OSError, ValueError):
            pass
        if not warned:
            log("  warte auf Scanner-Sichtung (Kamera-Menü offen? ble-watch läuft?)")
            warned = True
        await asyncio.sleep(1)
    return False


async def handshake(client, args):
    """Stage 2/3: CCCDs + 4-stage LSS handshake + name. Returns (s1, s2, s4) bytes."""

    # CCCD subscriptions first, exactly as the app: bleak picks indicate for 0x2000
    # (indicate-only) and notify for 0x2008 from the characteristic properties.
    def on_ind(tag):
        def cb(_c, data):
            log(f"  NOTIFY/IND {tag}  {hexs(bytes(data))}")

        return cb

    for uuid, tag in ((CONTROL_POINT, "2008"), (AUTH, "2000")):
        try:
            await client.start_notify(uuid, on_ind(tag))
            log(f"  CCCD {tag} subscribed")
        except Exception as exc:
            log(f"  CCCD {tag} failed: {type(exc).__name__}: {str(exc)[:60]}")

    dev = bytes.fromhex(args.device) if args.device else None
    non = bytes.fromhex(args.nonce) if args.nonce else None
    s1 = np.stage_one(dev, non)
    log(f"  stage 1  {hexs(s1.encode())}")
    await client.write_gatt_char(AUTH, s1.encode(), response=True)
    await asyncio.sleep(1.0)
    s2 = np.Message.decode(bytes(await client.read_gatt_char(AUTH)))
    log(f"  stage 2  {hexs(s2.encode())}")
    if s2.stage != 0x02:
        raise RuntimeError(f"no stage 2 (got 0x{s2.stage:02x})")
    s3 = np.stage_three(s1, s2)
    log(f"  salt #{np.find_salt(s1, s2)}  stage 3  {hexs(s3.encode())}")
    await client.write_gatt_char(AUTH, s3.encode(), response=True)
    await asyncio.sleep(1.0)
    s4 = np.Message.decode(bytes(await client.read_gatt_char(AUTH)))
    log(f"  stage 4  {hexs(s4.encode())}")
    if s4.stage != 0x04:
        raise RuntimeError(f"handshake rejected at stage 4 (got 0x{s4.stage:02x})")
    log(f"  -> authenticated; device={s1.device.hex()} nonce={s1.nonce.hex()}")
    if args.register:
        await client.write_gatt_char(NAME, np.client_name(args.register), response=True)
        log(f"  -> registered as {args.register!r}")
    return s1.encode(), s2.encode(), s4.encode()


def scan_wifi_for(ssid: str) -> bool:
    """True if the camera SSID is visible to this host now."""
    try:
        if IS_WINDOWS:
            netsh = r"C:\Windows\System32\netsh.exe"
            exe = netsh if os.path.exists("/mnt/c/Windows/System32/netsh.exe") else "netsh.exe"
            out = subprocess.run(
                [exe, "wlan", "show", "networks"], capture_output=True, text=True, timeout=20
            ).stdout
        else:
            out = subprocess.run(
                ["nmcli", "-t", "-f", "SSID", "dev", "wifi", "list"],
                capture_output=True,
                text=True,
                timeout=20,
            ).stdout
    except Exception as exc:
        log(f"  scan failed: {type(exc).__name__}: {str(exc)[:60]}")
        return False
    return ssid in out


async def run(args) -> int:
    log("Stage 1: classic bond")
    await ensure_bond(args.name)

    log("Stage 2: BLE connect + handshake")
    if args.wait_for_ad and not await wait_for_ad(args.timeout):
        log("  keine Scanner-Sichtung im Zeitfenster -- Kamera sendet nicht")
        return 2
    device = await find_camera(args.timeout)
    if device is None:
        log("  Kamera sendet nicht (Verbindungsmenü offen? Funk-Reset nötig?)")
        return 2
    async with BleakClient(device, timeout=args.timeout) as client:
        log(f"  connected mtu={client.mtu_size}")
        s1, s2, s4 = await handshake(client, args)

        log("Stage 3: power gate + credentials")
        power = bytes(await client.read_gatt_char(POWER))
        pname = POWER_TYPES.get(power[0] if power else 0xFF, "?")
        log(
            f"  0x2001 power = {hexs(power)}  {pname}"
            + ("  <-- ready" if pname == "VALID_WAKE" else "  <-- NOT ready")
        )
        config = bytes(await client.read_gatt_char(CONFIG))
        log(f"  0x2004 config = {len(config)}B flags=0x{(config[0] if config else 0):02x}")
        creds = None
        if lssec is not None and len(config) >= 97:
            try:
                creds = lssec.decrypt_config_from_handshake(s1, s2, s4, config)
                log(f"  -> SSID={creds.ssid!r}  Passwort={creds.password!r}")
                _write_creds(creds)  # for an external joiner (Mango): the pw rotates each session
            except Exception as exc:
                log(f"  cred decrypt failed: {type(exc).__name__}: {str(exc)[:60]}")
        elif lssec is None:
            log("  (lssec nicht importierbar -- Zugangsdaten nicht entschlüsselt)")

        # The credentials must be ready BEFORE establishment so we can join the
        # AP inside its short live window (it drops if no client joins in time).
        if creds and args.join:
            add_wifi_profile(creds.ssid, creds.password)

        log("Stage 4: establishment (WiFi)")
        await client.write_gatt_char(ESTABLISH, b"\x01", response=True)
        log("  0x2005 <- 01 (WiFi) accepted")

        # The AP is likely WiFi-Direct / a hidden SSID (never seen in a plain
        # scan), so don't wait to *see* it -- attempt the join right away, in a
        # tight loop, while BLE is still held.
        deadline = time.monotonic() + args.hold
        joined = False
        while time.monotonic() < deadline:
            visible = scan_wifi_for(creds.ssid) if creds else False
            # The SSID is hidden, so do NOT wait to see it -- try the join every
            # cycle while the camera holds the AP up.
            if creds and args.join and try_join(creds.ssid, creds.password):
                joined = True
                gw = wlan_gateway(creds.ssid)
                log(f"  WLAN verbunden mit {creds.ssid!r}  Kamera-IP≈{gw or '?'}")
                break
            # Do NOT break when the SSID becomes visible: dropping BLE here also
            # drops the camera AP before an external client (e.g. the Mango
            # repeater) can join. Hold the whole duration to keep the AP up.
            elapsed = args.hold - (deadline - time.monotonic())
            log(
                f"  +{elapsed:.0f}s: SSID {'im Scan' if visible else 'versteckt'}"
                f"{'; Join-Versuch...' if args.join else '; halte AP (fuer Mango)'}"
            )
            await asyncio.sleep(3.0)
        if not client.is_connected:
            log("  ! BLE getrennt (Kamera schaltet auf Funk um -- kann normal sein)")

    if not creds:
        log("Fertig (ohne Zugangsdaten -- lssec/Config prüfen).")
        return 0

    if args.join and joined:
        gw = wlan_gateway(creds.ssid) or "192.168.0.1"
        ok = ping(gw)
        log(f"  Ping {gw}: {'erreichbar' if ok else 'keine Antwort'}")
        log(f"  -> Live View als Nächstes: PTP/IP {gw}:15740 (OpenSession, StartLiveView 0x9201)")
        delete_wifi_profile(creds.ssid)
        return 0 if ok else 3

    if args.join:
        delete_wifi_profile(creds.ssid)
        log("  Beitritt im Zeitfenster nicht gelungen -- AP evtl. WiFi-Direct (P2P).")
    log("")
    log("Zugangsdaten (manueller Beitritt / Live View):")
    log(f"  SSID {creds.ssid}  ·  PTP/IP <kamera-ip>:15740")
    return 0


def _netsh() -> str:
    p = "/mnt/c/Windows/System32/netsh.exe"
    return p if os.path.exists(p) else "netsh.exe"


def _creds_path() -> str:
    import tempfile

    return os.path.join(tempfile.gettempdir(), "skyshutter_creds.txt")


def _write_creds(creds) -> None:
    """Write the session's fresh SSID+password so an external joiner (the Mango
    repeater) can use them -- the camera rotates the password every session."""
    try:
        with open(_creds_path(), "w") as fh:
            fh.write(f"{creds.ssid}\n{creds.password}\n")
    except OSError:
        pass


def _profile_path() -> str:
    """A temp path for the WLAN profile XML, valid for the Python that runs us
    (Windows Python -> a real C:\\...\\Temp path via tempfile)."""
    import tempfile

    return os.path.join(tempfile.gettempdir(), "skyshutter_ap.xml")


def add_wifi_profile(ssid: str, psk: str) -> None:
    if not IS_WINDOWS:
        # NetworkManager: hidden-SSID profile with the fresh key (idempotent).
        subprocess.run(
            ["nmcli", "connection", "delete", "id", ssid],
            capture_output=True,
            text=True,
            timeout=15,
        )
        subprocess.run(
            [
                "nmcli",
                "connection",
                "add",
                "type",
                "wifi",
                "ifname",
                "wlan0",
                "con-name",
                ssid,
                "ssid",
                ssid,
                "wifi.hidden",
                "yes",
                "802-11-wireless-security.key-mgmt",
                "wpa-psk",
                "802-11-wireless-security.psk",
                psk,
            ],
            capture_output=True,
            text=True,
            timeout=15,
        )
        return
    xml = (
        '<?xml version="1.0"?>\n'
        '<WLANProfile xmlns="http://www.microsoft.com/networking/WLAN/profile/v1">\n'
        f"  <name>{ssid}</name>\n"
        f"  <SSIDConfig><SSID><name>{ssid}</name></SSID>"
        "<nonBroadcast>true</nonBroadcast></SSIDConfig>\n"
        "  <connectionType>ESS</connectionType><connectionMode>manual</connectionMode>\n"
        "  <MSM><security>\n"
        "    <authEncryption><authentication>WPA2PSK</authentication>"
        "<encryption>AES</encryption><useOneX>false</useOneX></authEncryption>\n"
        f"    <sharedKey><keyType>passPhrase</keyType><protected>false</protected>"
        f"<keyMaterial>{psk}</keyMaterial></sharedKey>\n"
        "  </security></MSM>\n</WLANProfile>\n"
    )
    path = _profile_path()
    with open(path, "w") as fh:
        fh.write(xml)
    subprocess.run(
        [_netsh(), "wlan", "add", "profile", f"filename={path}"],
        capture_output=True,
        text=True,
        timeout=15,
    )


def delete_wifi_profile(ssid: str) -> None:
    if not IS_WINDOWS:
        subprocess.run(
            ["nmcli", "connection", "delete", "id", ssid],
            capture_output=True,
            text=True,
            timeout=15,
        )
        return
    subprocess.run(
        [_netsh(), "wlan", "delete", "profile", f"name={ssid}"],
        capture_output=True,
        text=True,
        timeout=15,
    )
    try:
        os.remove(_profile_path())
    except OSError:
        pass


def try_join(ssid: str, psk: str | None = None) -> bool:
    # The camera SSID is hidden, so the stored profile (with hidden=yes) makes
    # the adapter probe for it directly. On Linux this may drop the host's own
    # WiFi uplink for the duration -- acceptable, the stream runs locally.
    if not IS_WINDOWS:
        subprocess.run(
            ["nmcli", "connection", "up", "id", ssid, "ifname", "wlan0"],
            capture_output=True,
            text=True,
            timeout=25,
        )
        time.sleep(3)
        out = subprocess.run(
            ["nmcli", "-t", "-f", "GENERAL.CONNECTION,GENERAL.STATE", "dev", "show", "wlan0"],
            capture_output=True,
            text=True,
            timeout=15,
        ).stdout
        connected = f"GENERAL.CONNECTION:{ssid}" in out
        return connected
    subprocess.run(
        [_netsh(), "wlan", "connect", f"name={ssid}", f"ssid={ssid}"],
        capture_output=True,
        text=True,
        timeout=15,
    )
    time.sleep(3)
    out = subprocess.run(
        [_netsh(), "wlan", "show", "interfaces"], capture_output=True, text=True, timeout=15
    ).stdout.lower()
    return ssid.lower() in out and ("connected" in out or "verbunden" in out)


def _win_exe(name: str) -> str:
    p = f"/mnt/c/Windows/System32/{name}"
    return p if os.path.exists(p) else name


def wlan_gateway(ssid: str) -> str | None:
    if not IS_WINDOWS:
        out = subprocess.run(
            ["ip", "route", "show", "dev", "wlan0"],
            capture_output=True,
            text=True,
            timeout=15,
        ).stdout
        for line in out.splitlines():
            if line.startswith("default") and " via " in line:
                return line.split(" via ")[1].split()[0]
        return None
    out = subprocess.run(
        [_win_exe("ipconfig.exe")], capture_output=True, text=True, timeout=15
    ).stdout
    gw = None
    for line in out.splitlines():
        if "gateway" in line.lower():
            tail = line.split(":")[-1].strip()
            if tail.count(".") == 3:
                gw = tail
    return gw


def ping(host: str) -> bool:
    if not IS_WINDOWS:
        r = subprocess.run(
            ["ping", "-c", "2", "-W", "2", host],
            capture_output=True,
            text=True,
            timeout=15,
        )
        return "ttl=" in r.stdout.lower()
    r = subprocess.run(
        [_win_exe("PING.EXE"), "-n", "2", "-w", "1500", host],
        capture_output=True,
        text=True,
        timeout=15,
    )
    return "ttl=" in r.stdout.lower()


def main() -> int:
    p = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    p.add_argument("--name", default="P1100", help="paired-device name substring for bond check")
    p.add_argument("--register", metavar="NAME", help="write this client name to 0x2002")
    p.add_argument("--timeout", type=float, default=25.0, help="BLE scan/connect timeout")
    p.add_argument("--hold", type=float, default=60.0, help="seconds to hold BLE + watch the AP")
    p.add_argument("--join", action="store_true", help="also join the AP and open live view")
    p.add_argument(
        "--wait-for-ad",
        action="store_true",
        help="wait for the ble-watch scanner's fresh sighting instead of a one-shot scan",
    )
    p.add_argument("--device", help="reconnect with a known client device id (hex)")
    p.add_argument("--nonce", help="reconnect with a known client nonce (hex)")
    args = p.parse_args()
    return asyncio.run(run(args))


if __name__ == "__main__":
    sys.exit(main())
