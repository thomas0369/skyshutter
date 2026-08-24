#!/usr/bin/env python3
"""Pair a device directly over D-Bus -- bypassing bluetoothctl's own agent.

Measured 24.08. (FINDINGS): `bluetoothctl pair` registers its own session
agent; with stdin closed (script context) that agent auto-declines the SSP
user confirmation within ~2 ms -- the camera's code appears for a blink and
the pairing dies as AuthenticationFailed, while OUR DisplayYesNo auto-confirm
agent is never even asked. Calling org.bluez.Device1.Pair() over D-Bus leaves
our agent (bt-agent.py) as the only one in the game: it confirms, the human
presses OK on the camera display, the bond lands.

The Windows reference (tools/classic-pair.py, measured there 22.08.) never
pairs exactly once: the camera answers a bonding request only sometimes, so
the reference retries up to three times with a 2 s pause, and when custom
pairing stays unanswered it falls back to the OS's own routine. This tool
mirrors that on BlueZ: a retry loop around Pair(), then a fallback that
drops the device object, rediscovers the address over a classic inquiry and
pairs once more -- a failed bond can leave the old device object in a
half-connected HCI state that swallows further attempts.

    python3 tools/bt-pair.py 7C:B8:DA:A6:4F:FE [--timeout 35] [--attempts 3]

Runs under the system python3 (needs python3-dbus), root or with bus access.
"""

from __future__ import annotations

import argparse
import sys
import time

import dbus

BLUEZ = "org.bluez"
DEVICE1 = "org.bluez.Device1"
ADAPTER1 = "org.bluez.Adapter1"


def find_device(bus: dbus.SystemBus, address: str):
    om = dbus.Interface(bus.get_object(BLUEZ, "/"), "org.freedesktop.DBus.ObjectManager")
    for path, ifaces in om.GetManagedObjects().items():
        dev = ifaces.get(DEVICE1)
        if dev and str(dev.get("Address", "")).upper() == address.upper():
            return bus.get_object(BLUEZ, path), dev
    return None, None


def is_paired(bus: dbus.SystemBus, address: str) -> bool:
    _, dev = find_device(bus, address)
    return bool(dev and dev.get("Paired", False))


def adapter_of(device_path: str) -> str:
    """Adapter path for a device path (/org/bluez/hci0/dev_.. -> /org/bluez/hci0)."""
    marker = "/hci"
    cut = device_path.find(marker)
    if cut == -1:
        return "/org/bluez/hci0"
    rest = device_path[cut + len(marker) :]
    digits = ""
    for ch in rest:
        if ch.isdigit():
            digits += ch
        else:
            break
    return f"/org/bluez/hci{digits}"


def find_adapter(bus: dbus.SystemBus) -> str:
    om = dbus.Interface(bus.get_object(BLUEZ, "/"), "org.freedesktop.DBus.ObjectManager")
    for path, ifaces in om.GetManagedObjects().items():
        if ADAPTER1 in ifaces:
            return path
    return "/org/bluez/hci0"


def ensure_device(bus: dbus.SystemBus, address: str, wait_seconds: float):
    """Return the device object, creating it via BlueZ discovery if needed.

    Measured 24.08. evening: `hcitool inq` talks to the kernel directly and
    never creates a bluetoothd device object -- Pair() then dies as
    "not found" (rc=2 twice in a row). Discovery through bluetoothd (what
    `bluetoothctl scan on` does, plain StartDiscovery without a transport
    filter) creates the object; that path worked every time it was tried.
    """
    obj, _dev = find_device(bus, address)
    if obj is not None:
        return obj
    adapter = dbus.Interface(bus.get_object(BLUEZ, find_adapter(bus)), ADAPTER1)
    print(f"pair: Geraet {address} nicht in BlueZ -- Discovery bis zu {wait_seconds:.0f}s")
    adapter.StartDiscovery()
    deadline = time.monotonic() + wait_seconds
    try:
        while time.monotonic() < deadline:
            time.sleep(0.5)
            obj, _dev = find_device(bus, address)
            if obj is not None:
                return obj
    finally:
        try:
            adapter.StopDiscovery()
        except dbus.exceptions.DBusException:
            pass
    return None


def pair_call(obj, timeout: int) -> None:
    """One Device1.Pair() call; raises dbus.exceptions.DBusException on failure."""
    iface = dbus.Interface(obj, DEVICE1)
    iface.Pair(timeout=timeout * 1000, reply_timeout=timeout + 5)


def fallback_rediscover_and_pair(
    bus: dbus.SystemBus, address: str, wait_seconds: float, pair_timeout: int
) -> bool:
    """BlueZ equivalent of the reference's fallback (classic-pair.py 245-251).

    Remove the device object (clears the half-connected state a failed bond
    leaves behind), bring the address back through a classic inquiry and run
    one final Pair() on the fresh object.
    """
    obj, _dev = find_device(bus, address)
    hci = adapter_of(obj.object_path) if obj is not None else "/org/bluez/hci0"
    if obj is not None:
        dbus.Interface(bus.get_object(BLUEZ, hci), ADAPTER1).RemoveDevice(obj.object_path)
        print("fallback: Device-Objekt entfernt, frischer Inquiry laeuft ...")
    else:
        print(f"fallback: Adresse {address} unbekannt, Inquiry laeuft ...")

    adapter = dbus.Interface(bus.get_object(BLUEZ, hci), ADAPTER1)
    # No transport filter: plain discovery is the measured-working path
    # (24.08. evening); a bredr-only filter rediscovered nothing.
    adapter.StartDiscovery()
    fresh = None
    deadline = time.monotonic() + wait_seconds
    try:
        while time.monotonic() < deadline:
            time.sleep(0.5)
            fresh, _seen = find_device(bus, address)
            if fresh is not None:
                break
    finally:
        adapter.StopDiscovery()

    if fresh is None:
        print(f"fallback: Adresse {address} kam im Inquiry nicht zurueck")
        return False
    print("fallback: wieder gesehen -- letzter Pair()-Versuch auf frischem Objekt")
    pair_call(fresh, pair_timeout)
    return is_paired(bus, address)


def main() -> int:
    p = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    p.add_argument("address", help="BR/EDR address of the camera")
    p.add_argument("--timeout", type=int, default=35, help="seconds per Pair() call")
    p.add_argument(
        "--attempts",
        type=int,
        default=3,
        help="bonding tries; the camera often ignores the first (see classic-pair.py)",
    )
    p.add_argument("--pause", type=float, default=2.0, help="seconds between attempts")
    p.add_argument(
        "--no-fallback",
        action="store_true",
        help="skip the rediscover+pair fallback after the retry loop",
    )
    p.add_argument(
        "--discover",
        type=float,
        default=30.0,
        help="seconds of BlueZ discovery to create a missing device object",
    )
    args = p.parse_args()

    bus = dbus.SystemBus()
    obj = ensure_device(bus, args.address, args.discover)
    if obj is None:
        print(f"pair: Geraet {args.address} nicht gefunden (Discovery {args.discover:.0f}s leer)")
        return 2
    obj, dev = find_device(bus, args.address)
    if obj is None or dev is None:
        print(f"pair: Geraet {args.address} nicht gefunden (Scan laufen lassen)")
        return 2
    if bool(dev.get("Paired", False)):
        print(f"pair: {args.address} ist schon gepaart")
        return 0

    for attempt in range(1, args.attempts + 1):
        print(
            f"pair: Pair() Versuch {attempt}/{args.attempts} -- "
            "CODE AM KAMERA-DISPLAY JETZT BESTAETIGEN"
        )
        try:
            pair_call(obj, args.timeout)
        except dbus.exceptions.DBusException as exc:
            print(f"pair: Versuch {attempt} scheiterte: {exc.get_dbus_name()}")
        if is_paired(bus, args.address):
            print("pair: BOND_OK")
            return 0
        if attempt < args.attempts:
            time.sleep(args.pause)

    if args.no_fallback:
        print("pair: kein Bond -- Fallback uebersprungen (--no-fallback)")
        return 1

    print("pair: Pair() blieb ohne Bond -- Fallback (RemoveDevice + Inquiry + Pair)")
    try:
        if fallback_rediscover_and_pair(bus, args.address, 25, args.timeout):
            print("pair: BOND_OK (via Fallback)")
            return 0
    except dbus.exceptions.DBusException as exc:
        print(f"pair: Fallback D-Bus-Fehler: {exc.get_dbus_name()}: {exc.get_dbus_message()}")
    print("pair: kein Bond")
    return 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except dbus.exceptions.DBusException as exc:
        print(f"pair: D-Bus-Fehler: {exc.get_dbus_name()}: {exc.get_dbus_message()}")
        sys.exit(1)
