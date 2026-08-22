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
    from winrt.windows.storage.streams import DataReader
except ImportError:  # pragma: no cover - bench tool
    sys.exit("needs the Windows Python with the winrt packages")

DEFAULT_PREFIX = "P1100"


RESOLVED: dict[str, str] = {}
CAMERAS: set[str] = set()

#: Imaging / camera, as this camera reports it.
CAMERA_CLASS = 0x080620


def resolved_name(device) -> str:
    """Name as discovery finally saw it, which may differ from device.name."""
    return RESOLVED.get(device.id) or device.name or ""


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
    names: dict[str, str] = {}
    done = asyncio.Event()
    loop = asyncio.get_running_loop()

    async def name_of(device) -> str:
        """The device name, asking the radio if Windows has not resolved it.

        An inquiry often reports a device before its name arrives, and the
        camera showed up as '' more than once. Filtering on the empty name
        throws away exactly the device we are looking for.
        """
        if device.name:
            return device.name
        try:
            resolved = await BluetoothDevice.from_id_async(device.id)
        except Exception:
            return ""
        return resolved.name if resolved else ""

    async def consider(device) -> None:
        name = await name_of(device)
        # Windows often fails to resolve the name and substitutes
        # "Bluetooth <address>". The camera showed up that way, so matching on
        # the name alone misses it. Its class of device is the reliable mark:
        # 0x080620 is imaging/camera, and nothing else here reports that.
        klass = await class_of(device)
        looks_right = name.startswith(prefix) or klass == CAMERA_CLASS
        mark = "  <-- camera" if looks_right else ""
        state = "paired" if device.pairing.is_paired else "unpaired"
        extra = f" class=0x{klass:06x}" if klass else ""
        log(f"  {name!r}  {state}{extra}{mark}")
        names[device.id] = name
        RESOLVED[device.id] = name
        if looks_right:
            CAMERAS.add(device.id)
            done.set()

    async def class_of(device) -> int:
        try:
            resolved = await BluetoothDevice.from_id_async(device.id)
        except Exception:
            return 0
        return resolved.class_of_device.raw_value if resolved else 0

    def on_added(sender, device):
        if device.id in seen:
            return
        seen[device.id] = device
        asyncio.run_coroutine_threadsafe(consider(device), loop)

    def on_updated(sender, update):
        device = seen.get(update.id)
        if device is not None and not names.get(update.id):
            asyncio.run_coroutine_threadsafe(consider(device), loop)

    def on_completed(sender, _args):
        log("  inquiry round finished")

    # One watcher, left running for the whole window. Restarting it per round
    # was an experiment that made things worse: it then found nothing at all,
    # not even devices that were plainly in range.
    watcher.add_added(on_added)
    watcher.add_updated(on_updated)
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
    targets = [d for d in devices if d.id in CAMERAS or resolved_name(d).startswith(args.prefix)]
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
    # The camera answers a bonding request only sometimes. Measured: it either
    # asks for the code within about three seconds, or it stays silent and
    # Windows gives up after twenty-odd. Retrying costs nothing -- the device
    # is already found -- and turns an unreliable step into a reliable one.
    for attempt in range(1, args.attempts + 1):
        result = await custom.pair_async(kinds)
        status = result.status
        name = DevicePairingResultStatus(status).name
        log(f"result: {name}  (attempt {attempt}/{args.attempts})")
        if status == DevicePairingResultStatus.PAIRED:
            log("  -> bonded; the camera should now list this machine")
            return
        if attempt < args.attempts:
            await asyncio.sleep(2)
    log("  -> not bonded")


async def cmd_services(args) -> None:
    """Ask the camera what it offers over classic Bluetooth.

    After bonding it says "establishing connection" and waits. Either it wants
    to reach a service on our side, or it expects us to reach one on its side.
    This answers which, by reading its SDP records.
    """
    devices = await discover(args.prefix, args.seconds, paired=True)
    targets = [d for d in devices if d.id in CAMERAS or resolved_name(d).startswith(args.prefix)]
    if not targets:
        sys.exit(f"no paired device named {args.prefix}*")

    device = await BluetoothDevice.from_id_async(targets[0].id)
    if device is None:
        sys.exit("could not open the device")
    log(f"{device.name}  class=0x{device.class_of_device.raw_value:06x}")

    result = await device.get_rfcomm_services_async()
    log(f"{len(result.services)} RFCOMM service(s)")
    for service in result.services:
        log(f"  {service.service_id.as_string()}")
        attributes = await service.get_sdp_raw_attributes_async()
        for key in sorted(attributes):
            raw = bytes(DataReader.from_buffer(attributes[key]).read_buffer(
                attributes[key].length
            ))
            text = "".join(chr(c) if 32 <= c < 127 else "." for c in raw)
            log(f"      0x{key:04x}  {raw.hex()}  |{text}|")


async def cmd_forget(args) -> None:
    # Look at paired devices here -- the unpaired selector cannot see a bond
    # that already exists, which is the whole point of forgetting it.
    devices = await discover(args.prefix, args.seconds, paired=True)
    for device in devices:
        if device.id not in CAMERAS and not resolved_name(device).startswith(args.prefix):
            continue
        result = await device.pairing.unpair_async()
        log(f"unpair {device.name!r}: {DeviceUnpairingResultStatus(result.status).name}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--prefix", default=DEFAULT_PREFIX, help="name prefix to look for")
    parser.add_argument("--seconds", type=float, default=30.0, help="how long to sweep")
    parser.add_argument(
        "--attempts", type=int, default=3, help="bonding tries; the camera often ignores the first"
    )
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("list", help="show classic devices in range").set_defaults(run=cmd_list)
    sub.add_parser("pair", help="bond with the camera").set_defaults(run=cmd_pair)
    sub.add_parser("services", help="list the camera's own services").set_defaults(
        run=cmd_services
    )
    sub.add_parser("forget", help="drop an existing bond").set_defaults(run=cmd_forget)
    args = parser.parse_args()
    asyncio.run(args.run(args))


if __name__ == "__main__":
    main()
