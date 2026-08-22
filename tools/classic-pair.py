#!/usr/bin/env python3
"""Finish the pairing over classic Bluetooth.

The BLE handshake is only half of it. After it succeeds the camera makes
itself findable over *classic* Bluetooth, and the client has to run an
inquiry, find the device by name and bond with it. Only that bond puts the
client into the camera's device list -- which is why nothing we did over BLE
alone ever showed up there.

The reference implementation does exactly this: drop the BLE link, discover
classic devices, compare names verbatim, then bond. It also confirms the
numeric code automatically, because the camera shows the same digits and the
user presses OK there.

    python tools/classic-pair.py list
    python tools/classic-pair.py pair
    python tools/classic-pair.py forget

Run the BLE handshake first (ble-probe.py pairing); the camera only becomes
findable afterwards, and only while its menu is open.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import time

try:
    from winrt.windows.devices.bluetooth import BluetoothDevice
    from winrt.windows.devices.enumeration import (
        DeviceInformation,
        DevicePairingKinds,
        DevicePairingResultStatus,
        DeviceUnpairingResultStatus,
    )
except ImportError:  # pragma: no cover - bench tool
    sys.exit("needs the Windows Python with the winrt packages")

DEFAULT_PREFIX = "P1100"


def log(message: str) -> None:
    print(f"{time.strftime('%H:%M:%S')}  {message}", flush=True)


async def discover(prefix: str, seconds: float, paired: bool = False) -> list:
    """Run a real classic-Bluetooth inquiry.

    find_all_async only returns what Windows already has cached, which for
    unpaired devices is nothing. A DeviceWatcher is what actually puts the
    radio into inquiry, and the selector has to ask for the unpaired state
    explicitly -- the default selector means "paired only".
    """
    selector = BluetoothDevice.get_device_selector_from_pairing_state(paired)
    watcher = DeviceInformation.create_watcher_aqs_filter(selector)
    seen: dict[str, object] = {}
    done = asyncio.Event()
    loop = asyncio.get_running_loop()

    def on_added(sender, device):
        if device.id in seen:
            return
        seen[device.id] = device
        mark = "  <-- camera" if device.name.startswith(prefix) else ""
        state = "paired" if device.pairing.is_paired else "unpaired"
        log(f"  {device.name!r}  {state}{mark}")
        if device.name.startswith(prefix):
            loop.call_soon_threadsafe(done.set)

    def on_completed(sender, _args):
        log("  inquiry round finished")

    # One watcher, left running for the whole window. Restarting it per round
    # was an experiment that made things worse: it then found nothing at all,
    # not even devices that were plainly in range.
    watcher.add_added(on_added)
    watcher.add_enumeration_completed(on_completed)
    watcher.start()
    try:
        await asyncio.wait_for(done.wait(), timeout=seconds)
    except asyncio.TimeoutError:
        log(f"  no {prefix}* device after {seconds:.0f}s")
    finally:
        watcher.stop()
    return list(seen.values())


async def cmd_list(args) -> None:
    devices = await discover(args.prefix, args.seconds)
    log(f"{len(devices)} classic device(s) total")


async def cmd_pair(args) -> None:
    devices = await discover(args.prefix, args.seconds)
    targets = [d for d in devices if d.name.startswith(args.prefix)]
    if not targets:
        sys.exit(
            f"no classic device named {args.prefix}* -- run the BLE handshake first "
            "and keep the camera's menu open"
        )
    device = targets[0]
    log(f"pairing with {device.name!r}")

    if device.pairing.is_paired:
        log("  already paired -- use 'forget' first if you want a fresh bond")
        return

    custom = device.pairing.custom

    def on_pairing_requested(sender, request):
        # The camera shows the same digits and expects OK on its own body. The
        # published implementation confirms automatically for the same reason.
        kind = request.pairing_kind
        if kind == DevicePairingKinds.CONFIRM_PIN_MATCH:
            log(f"  *** code {request.pin} -- press OK on the camera now ***")
            request.accept()
        elif kind == DevicePairingKinds.CONFIRM_ONLY:
            log("  confirm-only request, accepting")
            request.accept()
        elif kind == DevicePairingKinds.PROVIDE_PIN:
            log("  camera wants a PIN, sending 0000")
            request.accept("0000")
        else:
            log(f"  unhandled pairing kind {kind}, accepting anyway")
            request.accept()

    custom.add_pairing_requested(on_pairing_requested)

    kinds = (
        DevicePairingKinds.CONFIRM_ONLY
        | DevicePairingKinds.CONFIRM_PIN_MATCH
        | DevicePairingKinds.PROVIDE_PIN
    )
    result = await custom.pair_async(kinds)
    status = result.status
    log(f"result: {DevicePairingResultStatus(status).name}")
    if status == DevicePairingResultStatus.PAIRED:
        log("  -> bonded; the camera should now list this machine")
    else:
        log("  -> not bonded")


async def cmd_forget(args) -> None:
    # Look at paired devices here -- the unpaired selector cannot see a bond
    # that already exists, which is the whole point of forgetting it.
    devices = await discover(args.prefix, args.seconds, paired=True)
    for device in devices:
        if not device.name.startswith(args.prefix):
            continue
        result = await device.pairing.unpair_async()
        log(f"unpair {device.name!r}: {DeviceUnpairingResultStatus(result.status).name}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--prefix", default=DEFAULT_PREFIX, help="name prefix to look for")
    parser.add_argument("--seconds", type=float, default=30.0, help="how long to sweep")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("list", help="show classic devices in range").set_defaults(run=cmd_list)
    sub.add_parser("pair", help="bond with the camera").set_defaults(run=cmd_pair)
    sub.add_parser("forget", help="drop an existing bond").set_defaults(run=cmd_forget)
    args = parser.parse_args()
    asyncio.run(args.run(args))


if __name__ == "__main__":
    main()
