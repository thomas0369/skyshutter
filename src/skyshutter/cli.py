"""Command line entry point: ``skyshutter <command>``."""

from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

from . import config, discovery
from .nikon import NikonCamera, NikonOperation
from .ptp import DeviceInfo, OperationCode, PtpError, ResponseCode, code_name
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
    _subparser(sub, "events", "poll the camera event queue until interrupted")

    shoot = _subparser(sub, "shoot", "release the shutter")
    shoot.add_argument("--af", action="store_true", help="autofocus before the exposure")
    shoot.add_argument("-n", "--count", type=int, default=1)
    shoot.add_argument("--interval", type=float, default=0.0, help="seconds between exposures")

    liveview = _subparser(sub, "liveview", "save live view frames to disk")
    liveview.add_argument("-o", "--out", type=Path, default=Path("liveview"))
    liveview.add_argument("-n", "--frames", type=int, default=10)
    liveview.add_argument("--fps", type=float, default=10.0)

    stream = _subparser(sub, "stream", "serve the live view as MJPEG over HTTP")
    stream.add_argument("--bind", default="0.0.0.0")
    stream.add_argument("--http-port", type=_int, default=8080)
    stream.add_argument("--fps", type=float, default=15.0)

    raw = _subparser(sub, "raw", "send an arbitrary PTP operation (protocol spelunking)")
    raw.add_argument("opcode", type=_int)
    raw.add_argument("params", type=_int, nargs="*")
    raw.add_argument("-o", "--out", type=Path, help="write the data phase to this file")
    raw.add_argument("--no-session", action="store_true", help="skip OpenSession")

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


def cmd_shoot(args: argparse.Namespace) -> int:
    with NikonCamera.open(
        _resolve_host(args),
        port=args.port,
        guid=config.client_guid(args.guid),
        friendly_name=config.client_name(args.name),
        timeout=args.timeout,
    ) as camera:
        for index in range(args.count):
            if args.af:
                camera.autofocus()
            camera.capture()
            print(f"exposure {index + 1}/{args.count} triggered")
            if args.interval and index + 1 < args.count:
                time.sleep(args.interval)
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
            for frame in camera.stream_live_view(fps=args.fps):
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
        result = connection.transaction(
            args.opcode, tuple(args.params), raise_on_error=False
        )
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


COMMANDS = {
    "probe": cmd_probe,
    "info": cmd_info,
    "events": cmd_events,
    "shoot": cmd_shoot,
    "liveview": cmd_liveview,
    "stream": cmd_stream,
    "raw": cmd_raw,
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
    except (PtpError, PtpIpError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except OSError as exc:
        print(f"network error: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
