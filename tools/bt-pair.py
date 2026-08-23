#!/usr/bin/env python3
"""Pair a device directly over D-Bus -- bypassing bluetoothctl's own agent.

Measured 24.08. (FINDINGS): `bluetoothctl pair` registers its own session
agent; with stdin closed (script context) that agent auto-declines the SSP
user confirmation within ~2 ms -- the camera's code appears for a blink and
the pairing dies as AuthenticationFailed, while OUR DisplayYesNo auto-confirm
agent is never even asked. Calling org.bluez.Device1.Pair() over D-Bus leaves
our agent (bt-agent.py) as the only one in the game: it confirms, the human
presses OK on the camera display, the bond lands.

    python3 tools/bt-pair.py 7C:B8:DA:A6:4F:FE [--timeout 30]

Runs under the system python3 (needs python3-dbus), root or with bus access.
"""

from __future__ import annotations

import argparse
import sys
import time

import dbus

BLUEZ = "org.bluez"
DEVICE1 = "org.bluez.Device1"


def find_device(bus: dbus.SystemBus, address: str):
    om = dbus.Interface(bus.get_object(BLUEZ, "/"), "org.freedesktop.DBus.ObjectManager")
    for path, ifaces in om.GetManagedObjects().items():
        dev = ifaces.get(DEVICE1)
        if dev and str(dev.get("Address", "")).upper() == address.upper():
            return bus.get_object(BLUEZ, path), dev
    return None, None


def main() -> int:
    p = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    p.add_argument("address", help="BR/EDR address of the camera")
    p.add_argument("--timeout", type=int, default=35, help="seconds to wait for Pair()")
    args = p.parse_args()

    bus = dbus.SystemBus()
    obj, dev = find_device(bus, args.address)
    if obj is None or dev is None:
        print(f"pair: Geraet {args.address} nicht gefunden (Scan laufen lassen)")
        return 2
    if bool(dev.get("Paired", False)):
        print(f"pair: {args.address} ist schon gepaart")
        return 0

    print(f"pair: Pair() auf {args.address} -- CODE AM KAMERA-DISPLAY JETZT BESTAETIGEN")
    iface = dbus.Interface(obj, DEVICE1)
    iface.Pair(timeout=args.timeout * 1000, reply_timeout=args.timeout + 5)
    # Pair() returns on success or raises dbus.exceptions.DBusException

    obj2, dev2 = find_device(bus, args.address)
    if dev2 and bool(dev2.get("Paired", False)):
        print("pair: BOND_OK")
        return 0
    print("pair: Pair() kehrte zurueck ohne Bond")
    return 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except dbus.exceptions.DBusException as exc:
        print(f"pair: D-Bus-Fehler: {exc.get_dbus_name()}: {exc.get_dbus_message()}")
        sys.exit(1)
