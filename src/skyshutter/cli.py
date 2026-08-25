"""Command line entry point: ``skyshutter <command>``."""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from pathlib import Path

from . import btsnoop, config, discovery, lssec
from .nikon import NikonCamera, NikonOperation
from .ptp import AccessCapability, DeviceInfo, OperationCode, PtpError, ResponseCode, code_name
from .ptpip import DEFAULT_PORT, PtpIpConnection, PtpIpError

log = logging.getLogger("skyshutter")


def _int(value: str) -> int:
    """Accept 0x9203 as well as 37379."""
    return int(value, 0)


# Connection options are accepted before *and* after the subcommand, because
# "skyshutter probe --host ..." is what everybody types first.  The defaults are
# applied in main(), not by argparse, so that the subparser cannot reset a value
# that was given ahead of the subcommand.
COMMON_DEFAULTS: dict[str, object] = {
    "host": None,
    "port": DEFAULT_PORT,
    "guid": None,
    "name": None,
    "timeout": 10.0,
    "verbose": 0,
}


def _add_common_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--host", default=argparse.SUPPRESS, help="camera address (default: auto detect)"
    )
    parser.add_argument("--port", type=_int, default=argparse.SUPPRESS)
    parser.add_argument(
        "--guid", default=argparse.SUPPRESS, help="client GUID (default: stored identity)"
    )
    parser.add_argument(
        "--name", default=argparse.SUPPRESS, help="client friendly name (default: skyshutter)"
    )
    parser.add_argument("--timeout", type=float, default=argparse.SUPPRESS)
    parser.add_argument("-v", "--verbose", action="count", default=argparse.SUPPRESS)


def _subparser(
    sub: argparse._SubParsersAction, name: str, help_text: str
) -> argparse.ArgumentParser:
    parser = sub.add_parser(name, help=help_text)
    _add_common_options(parser)
    return parser


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="skyshutter",
        description="Control a Nikon camera over its own WiFi (PTP/IP).",
    )
    _add_common_options(parser)

    sub = parser.add_subparsers(dest="command", required=True)

    probe = _subparser(sub, "probe", "scan the camera for open ports and try PTP/IP")
    probe.add_argument("--ports", type=_int, nargs="*", help="ports to scan (default: known set)")
    probe.add_argument("--scan-timeout", type=float, default=1.0)

    _subparser(sub, "info", "dump DeviceInfo, including supported operations")
    props = _subparser(sub, "props", "list the device properties and storage")
    props.add_argument("--json", action="store_true", help="print as JSON")
    props.add_argument(
        "--dump",
        nargs="?",
        const="auto",
        metavar="FILE",
        help="write every property value as JSON (default name: props-<timestamp>.json)",
    )
    props.add_argument(
        "--diff",
        nargs=2,
        metavar=("BEFORE", "AFTER"),
        help="compare two dumps offline -- no camera connection needed",
    )
    _subparser(sub, "events", "poll the camera event queue until interrupted")

    shoot = _subparser(sub, "shoot", "release the shutter")
    shoot.add_argument("--af", action="store_true", help="autofocus before the exposure")
    shoot.add_argument("-n", "--count", type=int, default=1)
    shoot.add_argument("--interval", type=float, default=0.0, help="seconds between exposures")
    shoot.add_argument("--get", action="store_true", help="download the images taken by this run")
    shoot.add_argument(
        "-o", "--out", type=Path, default=Path("."), help="output directory with --get"
    )

    download = _subparser(sub, "download", "fetch images from the card via GetPartialObject")
    download.add_argument("--last", type=int, default=1, help="how many of the newest images")
    download.add_argument("-o", "--out", type=Path, default=Path("."), help="output directory")
    download.add_argument("--list", action="store_true", help="only list objects, fetch nothing")
    download.add_argument(
        "--preview",
        action="store_true",
        help="fetch the 8 MP preview (0x9522) instead of the full file",
    )

    set_parser = _subparser(sub, "set", "change an exposure setting on the camera")
    set_parser.add_argument(
        "what",
        choices=["shutter", "iso", "aperture", "ev", "program", "drive", "afarea"],
    )
    set_parser.add_argument("value", nargs="+", help="value(s) for the setting")
    set_parser.add_argument("--show", action="store_true", help="only print the current value")

    liveview = _subparser(sub, "liveview", "save live view frames to disk")
    liveview.add_argument("-o", "--out", type=Path, default=Path("liveview"))
    liveview.add_argument("-n", "--frames", type=int, default=10)
    liveview.add_argument("--fps", type=float, default=10.0)

    stream = _subparser(sub, "stream", "serve the live view as MJPEG over HTTP")
    stream.add_argument("--bind", default="0.0.0.0")
    stream.add_argument("--http-port", type=_int, default=8080)
    stream.add_argument("--fps", type=float, default=15.0)
    stream.add_argument(
        "--remote",
        action="store_true",
        help="enter app-style remote mode (ControlMode 1): small ~36 KB frames, fast",
    )

    raw = _subparser(sub, "raw", "send an arbitrary PTP operation (protocol spelunking)")
    raw.add_argument("opcode", type=_int)
    raw.add_argument("params", type=_int, nargs="*")
    raw.add_argument("-o", "--out", type=Path, help="write the data phase to this file")
    raw.add_argument("--no-session", action="store_true", help="skip OpenSession")

    # Not a camera command: it works on pairing bytes, so no connection options.
    wifi = sub.add_parser(
        "wifi", help="decrypt the camera's WiFi SSID and password from the pairing"
    )
    wifi.add_argument(
        "pairing",
        type=Path,
        nargs="?",
        help="JSON from the pairing run (stage1/stage2/stage4/config as hex)",
    )
    wifi.add_argument("--stage1", help="stage 1 handshake message, hex (ours)")
    wifi.add_argument("--stage2", help="stage 2 handshake message, hex (camera)")
    wifi.add_argument("--stage4", help="stage 4 handshake message, hex (camera)")
    wifi.add_argument("--config", help="the 0x2004 connection-configuration blob, hex")
    wifi.add_argument(
        "--connect",
        action="store_true",
        help="print an nmcli line to join the network, do not run it",
    )

    # Not a camera command: it reads a file, so it skips the connection options.
    snoop = sub.add_parser("btsnoop", help="decode the ATT/GATT traffic in a Bluetooth capture")
    snoop.add_argument("path", type=Path, help="btsnoop_hci.log, or the bugreport zip holding it")
    snoop.add_argument(
        "--redact", action="store_true", help="hide values — use before quoting a capture publicly"
    )
    snoop.add_argument(
        "--strings", action="store_true", help="only show packets carrying readable text"
    )
    snoop.add_argument("--handles", action="store_true", help="list the discovered handles instead")

    return parser


def _connection(args: argparse.Namespace, host: str) -> PtpIpConnection:
    return PtpIpConnection(
        host,
        port=args.port,
        guid=config.client_guid(args.guid),
        friendly_name=config.client_name(args.name),
        timeout=args.timeout,
    )


def _resolve_host(args: argparse.Namespace) -> str:
    if args.host:
        return args.host
    log.info("no --host given, looking for a camera on %s", ", ".join(discovery.LIKELY_HOSTS))
    host = discovery.find_camera()
    if host is None:
        raise SystemExit(
            "no camera found. Join the camera's WiFi first, then pass --host explicitly."
        )
    log.info("found camera at %s", host)
    return host


def cmd_probe(args: argparse.Namespace) -> int:
    hosts = [args.host] if args.host else list(discovery.LIKELY_HOSTS)
    found = False
    for host in hosts:
        result = discovery.probe(
            host,
            guid=config.client_guid(args.guid),
            name=config.client_name(args.name),
            port=args.port,
            timeout=args.scan_timeout,
            ports=args.ports,
        )
        if result.open_ports or args.host:
            print(result.summary())
        found = found or bool(result.open_ports)
    if not found:
        print("nothing reachable. Is this machine joined to the camera's WiFi?")
        return 1
    return 0


def _print_device_info(info: DeviceInfo) -> None:
    print(f"model            {info.model}")
    print(f"manufacturer     {info.manufacturer}")
    print(f"firmware         {info.device_version}")
    print(f"serial           {info.serial_number}")
    print(f"standard version {info.standard_version / 100:.2f}")
    print(
        f"vendor extension 0x{info.vendor_extension_id:08X} "
        f"v{info.vendor_extension_version} {info.vendor_extension_desc}"
    )
    print(f"\noperations supported ({len(info.operations_supported)}):")
    for opcode in sorted(info.operations_supported):
        enum_cls = NikonOperation if opcode >= 0x9000 else OperationCode
        print(f"  0x{opcode:04X}  {code_name(opcode, enum_cls)}")
    print(f"\nevents supported ({len(info.events_supported)}):")
    print("  " + " ".join(f"0x{code:04X}" for code in sorted(info.events_supported)))
    print(f"\ndevice properties ({len(info.device_properties_supported)}):")
    print("  " + " ".join(f"0x{code:04X}" for code in sorted(info.device_properties_supported)))


def cmd_info(args: argparse.Namespace) -> int:
    with NikonCamera.open(
        _resolve_host(args),
        port=args.port,
        guid=config.client_guid(args.guid),
        friendly_name=config.client_name(args.name),
        timeout=args.timeout,
    ) as camera:
        assert camera.device_info is not None
        _print_device_info(camera.device_info)
    return 0


def _access_name(access: int) -> str:
    if access == AccessCapability.GET_SET:
        return "read/write"
    return "read-only"


def _gib(n: int) -> str:
    return f"{n / 1024**3:.1f} GiB"


def _prop_snapshot(camera: NikonCamera) -> dict:
    """Everything a dump records: values, descriptors, storage, time."""
    props = camera.properties()
    return {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "properties": {
            f"0x{code:04X}": {
                "data_type": f"0x{d.data_type:04X}",
                "access": _access_name(d.access),
                "default": d.default_value,
                "current": d.current_value,
                "min": d.minimum,
                "max": d.maximum,
                "step": d.step,
                "values": d.enumeration,
            }
            for code, d in sorted(props.items())
        },
        "storage": {
            f"0x{sid:08X}": {
                "max_capacity": s.max_capacity,
                "free_space_bytes": s.free_space_bytes,
                "free_space_objects": s.free_space_objects,
            }
            for sid, s in ((sid, camera.storage_info(sid)) for sid in camera.storage_ids())
        },
    }


def _diff_snapshots(before_path: Path, after_path: Path) -> int:
    before = json.loads(before_path.read_text())
    after = json.loads(after_path.read_text())
    codes = sorted(set(before.get("properties", {})) | set(after.get("properties", {})))
    changes = []
    for code in codes:
        b = before.get("properties", {}).get(code, {})
        a = after.get("properties", {}).get(code, {})
        for field in ("current", "default"):
            if b.get(field) != a.get(field):
                changes.append((code, field, b.get(field), a.get(field)))
    if not changes:
        print("no property changes")
        return 0
    print(f"{len(changes)} change(s):")
    for code, field, old, new in changes:
        print(f"  {code}  {field}: {old!r} -> {new!r}")
    return 0


def cmd_props(args: argparse.Namespace) -> int:
    if args.diff:
        return _diff_snapshots(Path(args.diff[0]), Path(args.diff[1]))
    with NikonCamera.open(
        _resolve_host(args),
        port=args.port,
        guid=config.client_guid(args.guid),
        friendly_name=config.client_name(args.name),
        timeout=args.timeout,
    ) as camera:
        if args.dump:
            snapshot = _prop_snapshot(camera)
            path = (
                Path(time.strftime("props-%Y%m%d-%H%M%S.json"))
                if args.dump == "auto"
                else Path(args.dump)
            )
            path.write_text(json.dumps(snapshot, indent=2))
            print(f"{len(snapshot['properties'])} properties -> {path}")
            return 0
        props = camera.properties()
        storage = {sid: camera.storage_info(sid) for sid in camera.storage_ids()}

        if args.json:
            payload = {
                "properties": {
                    f"0x{code:04X}": {
                        "data_type": f"0x{d.data_type:04X}",
                        "access": _access_name(d.access),
                        "default": d.default_value,
                    }
                    for code, d in sorted(props.items())
                },
                "storage": {
                    f"0x{sid:08X}": {
                        "max_capacity": s.max_capacity,
                        "free_space_bytes": s.free_space_bytes,
                        "free_space_objects": s.free_space_objects,
                    }
                    for sid, s in storage.items()
                },
            }
            print(json.dumps(payload, indent=2))
            return 0

        print(f"properties ({len(props)}):")
        for code, d in sorted(props.items()):
            default = f"  default {d.default_value}" if d.default_value is not None else ""
            print(f"  0x{code:04X}  0x{d.data_type:04X}  {_access_name(d.access)}{default}")
        print(f"\nstorage ({len(storage)}):")
        for sid, s in storage.items():
            print(
                f"  0x{sid:08X}  {_gib(s.max_capacity)} total, "
                f"{_gib(s.free_space_bytes)} free, {s.free_space_objects} objects"
            )
    return 0


def cmd_events(args: argparse.Namespace) -> int:
    with NikonCamera.open(
        _resolve_host(args),
        port=args.port,
        guid=config.client_guid(args.guid),
        friendly_name=config.client_name(args.name),
        timeout=args.timeout,
    ) as camera:
        print("polling for events, ctrl-c to stop")
        try:
            while True:
                for code, param in camera.get_events():
                    print(f"event 0x{code:04X} param 0x{param:08X}")
                packet = camera.connection.poll_event(timeout=0.5)
                if packet is not None:
                    print(f"event channel: {packet.type_name} {packet.payload.hex()}")
        except KeyboardInterrupt:
            print()
    return 0


def _fetch_objects(camera: NikonCamera, infos: list, out: Path, preview: bool = False) -> None:
    out.mkdir(parents=True, exist_ok=True)
    for info in infos:
        if preview:
            data = camera.preview(info.handle)
            path = out / f"{info.filename.rsplit('.', 1)[0]}_8mp.jpg"
        else:
            data = camera.download(info.handle, info.compressed_size)
            path = out / info.filename
        path.write_bytes(data)
        print(f"{info.filename}: {len(data) / 1e6:.1f} MB -> {path}")


def cmd_shoot(args: argparse.Namespace) -> int:
    with NikonCamera.open(
        _resolve_host(args),
        port=args.port,
        guid=config.client_guid(args.guid),
        friendly_name=config.client_name(args.name),
        timeout=args.timeout,
    ) as camera:
        before = set(camera.object_handles()) if args.get else set()
        for index in range(args.count):
            if args.af:
                camera.autofocus()
            camera.capture()
            print(f"exposure {index + 1}/{args.count} triggered")
            if args.interval and index + 1 < args.count:
                time.sleep(args.interval)
        if args.get:
            fresh = [h for h in camera.object_handles() if h not in before]
            if not fresh:
                print("no new objects appeared on the card")
                return 0
            _fetch_objects(camera, [camera.object_info(h) for h in fresh], args.out)
    return 0


def cmd_download(args: argparse.Namespace) -> int:
    with NikonCamera.open(
        _resolve_host(args),
        port=args.port,
        guid=config.client_guid(args.guid),
        friendly_name=config.client_name(args.name),
        timeout=args.timeout,
    ) as camera:
        handles = camera.object_handles()
        if not handles:
            print("no objects on the card")
            return 0
        infos = [camera.object_info(handle) for handle in handles]
        if args.list:
            for info in infos:
                print(f"{info.handle:#010x}  {info.compressed_size:>10} B  {info.filename}")
            return 0
        _fetch_objects(camera, infos[-args.last :], args.out, preview=args.preview)
    return 0


def cmd_set(args: argparse.Namespace) -> int:
    from .nikon import BULB_SHUTTER, DriveMode, ExposureProgram

    program_names = {
        "M": ExposureProgram.MANUAL,
        "P": ExposureProgram.PROGRAM_AUTO,
        "A": ExposureProgram.APERTURE_PRIORITY,
        "S": ExposureProgram.SHUTTER_PRIORITY,
    }
    drive_names = {"single": DriveMode.SINGLE, "burst": DriveMode.BURST}

    with NikonCamera.open(
        _resolve_host(args),
        port=args.port,
        guid=config.client_guid(args.guid),
        friendly_name=config.client_name(args.name),
        timeout=args.timeout,
    ) as camera:
        what, value = args.what, args.value
        if what == "shutter":
            if args.show:
                num, den = camera.shutter_speed()
                print("bulb" if (num, den) == BULB_SHUTTER else f"{num}/{den} s")
                return 0
            text = value[0].lower()
            if text == "bulb":
                camera.set_shutter_speed(*BULB_SHUTTER)
            elif "/" in text:
                num, den = text.split("/", 1)
                camera.set_shutter_speed(int(num), int(den))
            else:
                camera.set_shutter_speed(1, int(text.removeprefix("s")))
        elif what == "iso":
            if args.show:
                print(camera.iso())
                return 0
            camera.set_iso(int(value[0]))
        elif what == "aperture":
            if args.show:
                print(f"f/{camera.aperture():.1f}")
                return 0
            camera.set_aperture(float(value[0]))
        elif what == "ev":
            if args.show:
                print(f"{camera.exposure_bias():+.1f} EV")
                return 0
            camera.set_exposure_bias(float(value[0]))
        elif what == "program":
            if args.show:
                print(camera.exposure_program().name)
                return 0
            camera.set_exposure_program(program_names[value[0].upper()])
        elif what == "drive":
            if args.show:
                print(camera.drive_mode().name)
                return 0
            name = value[0].lower()
            if name in drive_names:
                camera.set_drive_mode(drive_names[name])
            else:
                camera.set_drive_mode(DriveMode(int(name)))
        elif what == "afarea":
            if len(value) != 2:
                print("afarea needs x and y", file=sys.stderr)
                return 2
            camera.set_af_area(int(value[0]), int(value[1]))
        print(f"{what} set")
    return 0


def cmd_liveview(args: argparse.Namespace) -> int:
    args.out.mkdir(parents=True, exist_ok=True)
    saved = 0
    with NikonCamera.open(
        _resolve_host(args),
        port=args.port,
        guid=config.client_guid(args.guid),
        friendly_name=config.client_name(args.name),
        timeout=args.timeout,
    ) as camera:
        for frame in camera.stream_live_view(fps=args.fps):
            path = args.out / f"frame_{saved:05d}.jpg"
            path.write_bytes(frame)
            saved += 1
            print(f"{path} ({len(frame)} bytes)")
            if saved >= args.frames:
                break
    return 0 if saved else 1


def cmd_stream(args: argparse.Namespace) -> int:
    from .mjpeg import FrameBuffer, serve

    buffer = FrameBuffer()
    server = serve(buffer, host=args.bind, port=args.http_port)
    print(f"live view on http://{args.bind}:{args.http_port}/ (ctrl-c to stop)")
    try:
        with NikonCamera.open(
            _resolve_host(args),
            port=args.port,
            guid=config.client_guid(args.guid),
            friendly_name=config.client_name(args.name),
            timeout=args.timeout,
        ) as camera:
            for frame in camera.stream_live_view(
                fps=args.fps, remote_mode=getattr(args, "remote", False)
            ):
                buffer.publish(frame)
    except KeyboardInterrupt:
        print()
    finally:
        buffer.close()
        server.shutdown()
    return 0


def cmd_raw(args: argparse.Namespace) -> int:
    connection = _connection(args, _resolve_host(args))
    connection.connect()
    try:
        if not args.no_session:
            connection.open_session()
        result = connection.transaction(args.opcode, tuple(args.params), raise_on_error=False)
        print(
            f"response {code_name(result.response_code, ResponseCode)} "
            f"[0x{result.response_code:04X}]"
        )
        if result.parameters:
            print("params   " + " ".join(f"0x{p:08X}" for p in result.parameters))
        print(f"data     {len(result.data)} bytes")
        if result.data:
            if args.out:
                args.out.write_bytes(result.data)
                print(f"written  {args.out}")
            else:
                preview = result.data[:256]
                print(preview.hex(" ", 1))
                if len(result.data) > len(preview):
                    print(f"... ({len(result.data) - len(preview)} more bytes)")
        return 0 if result.ok else 1
    finally:
        if not args.no_session:
            connection.close_session()
        connection.close()


def cmd_btsnoop(args: argparse.Namespace) -> int:
    capture = btsnoop.parse(args.path)

    if args.handles:
        if not capture.handle_uuids:
            print("no handles discovered — the capture missed the service discovery")
            return 1
        for handle in sorted(capture.handle_uuids):
            print(f"0x{handle:04x}  {capture.handle_uuids[handle]}")
        return 0

    shown = 0
    for packet in capture.packets:
        if args.strings and not btsnoop.printable_strings(packet.value):
            continue
        print(btsnoop.format_packet(capture, packet, redact=args.redact))
        shown += 1

    print(
        f"\n{capture.records} records, {len(capture.packets)} ATT packets, "
        f"{shown} shown, {len(capture.handle_uuids)} handles discovered",
        file=sys.stderr,
    )
    return 0 if capture.packets else 1


def cmd_wifi(args: argparse.Namespace) -> int:
    """Recover the camera's WiFi credentials from what pairing captured.

    Reads the three handshake messages and the 0x2004 blob -- either from a
    JSON file the pairing tool wrote, or from --stage1/--stage2/--stage4/--config
    on the command line -- and prints the SSID and password. Nothing here talks
    to the camera; it is pure decryption of bytes already in hand.
    """
    fields = {
        "stage1": args.stage1,
        "stage2": args.stage2,
        "stage4": args.stage4,
        "config": args.config,
    }
    if args.pairing is not None:
        data = json.loads(args.pairing.read_text())
        for key in fields:
            fields[key] = fields[key] or data.get(key)

    missing = [k for k, v in fields.items() if not v]
    if missing:
        print(
            f"error: missing {', '.join(missing)} -- pass a pairing JSON or the "
            "--stage1/--stage2/--stage4/--config options",
            file=sys.stderr,
        )
        return 1

    try:
        raw = {k: bytes.fromhex(v.replace(" ", "")) for k, v in fields.items()}
    except ValueError as exc:
        print(f"error: not valid hex: {exc}", file=sys.stderr)
        return 1

    cred = lssec.decrypt_config_from_handshake(
        raw["stage1"], raw["stage2"], raw["stage4"], raw["config"]
    )
    if not cred.ssid:
        print(
            "error: decryption produced an empty SSID -- wrong handshake values?", file=sys.stderr
        )
        return 1

    print(f"SSID      {cred.ssid}")
    print(f"password  {cred.password}")
    if args.connect:
        # Printed, not run: joining the camera's network drops the link this
        # session may be running over, so leave that decision to the operator.
        print(
            f"\n# to join the camera's network:\n"
            f"nmcli device wifi connect {cred.ssid!r} password {cred.password!r}"
        )
    return 0


COMMANDS = {
    "probe": cmd_probe,
    "info": cmd_info,
    "props": cmd_props,
    "events": cmd_events,
    "shoot": cmd_shoot,
    "download": cmd_download,
    "set": cmd_set,
    "liveview": cmd_liveview,
    "stream": cmd_stream,
    "raw": cmd_raw,
    "wifi": cmd_wifi,
    "btsnoop": cmd_btsnoop,
}


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    for option, default in COMMON_DEFAULTS.items():
        if not hasattr(args, option):
            setattr(args, option, default)
    logging.basicConfig(
        level={0: logging.WARNING, 1: logging.INFO}.get(args.verbose, logging.DEBUG),
        format="%(levelname)s %(name)s: %(message)s",
    )
    try:
        return COMMANDS[args.command](args)
    except (PtpError, PtpIpError, btsnoop.BtsnoopError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except OSError as exc:
        print(f"network error: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
