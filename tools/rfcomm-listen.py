#!/usr/bin/env python3
"""Offer the serial service the camera connects back to after pairing.

Bonding is not the end of it. Once the bond exists the camera opens a classic
Bluetooth serial connection to the client -- the reference implementation
keeps an SPP server running for exactly this and then waits. Without one the
camera sits on "establishing connection" forever, which is what it does to us.

This puts up an RFCOMM serial port, advertises it over SDP, and dumps every
byte that arrives. Whatever the camera says on that channel is the next thing
we do not know yet.

    python tools/rfcomm-listen.py

Pair first (classic-pair.py pair), then start this and let the camera retry.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import time

try:
    from winrt.windows.devices.bluetooth.rfcomm import RfcommServiceId, RfcommServiceProvider
    from winrt.windows.networking.sockets import (
        SocketProtectionLevel,
        StreamSocketListener,
    )
    from winrt.windows.storage.streams import DataReader, DataWriter
except ImportError:  # pragma: no cover - bench tool
    sys.exit("needs winrt-Windows.Devices.Bluetooth.Rfcomm and winrt-Windows.Networking.Sockets")


def log(message: str) -> None:
    print(f"{time.strftime('%H:%M:%S')}  {message}", flush=True)


def hexdump(data: bytes) -> str:
    text = "".join(chr(c) if 32 <= c < 127 else "." for c in data)
    return f"{len(data):3}B  {data.hex()}  |{text}|"


async def serve(args) -> None:
    provider = await RfcommServiceProvider.create_async(RfcommServiceId.serial_port)
    listener = StreamSocketListener()
    sockets: list = []

    def on_connection(sender, event):
        socket = event.socket
        sockets.append(socket)
        host = socket.information.remote_host_name
        log(f"CONNECTED from {host.display_name if host else '?'}")

    listener.add_connection_received(on_connection)
    await listener.bind_service_name_with_protection_level_async(
        provider.service_id.as_string(), SocketProtectionLevel.PLAIN_SOCKET
    )

    # Minimal SDP record: a service name, so the camera sees a serial port.
    writer = DataWriter()
    name = args.service_name.encode("utf-8")
    writer.write_byte(0x25)  # text string, 8-bit length follows
    writer.write_byte(len(name))
    writer.write_bytes(name)
    provider.sdp_raw_attributes.insert(0x0100, writer.detach_buffer())

    provider.start_advertising_with_radio_discoverability(listener, True)
    log(f"serial service up, advertised as {args.service_name!r}")
    log("waiting for the camera to connect -- ctrl-c to stop")

    try:
        while True:
            await asyncio.sleep(0.2)
            for socket in list(sockets):
                reader = DataReader(socket.input_stream)
                reader.input_stream_options = 1  # partial: return what is there
                try:
                    count = await reader.load_async(4096)
                except Exception as exc:
                    log(f"read failed: {type(exc).__name__}: {str(exc)[:70]}")
                    sockets.remove(socket)
                    continue
                if count:
                    payload = bytes(reader.read_buffer(count))
                    log(f"RECV {hexdump(payload)}")
    except KeyboardInterrupt:
        pass
    finally:
        provider.stop_advertising()
        log("stopped")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--service-name", default="skyshutter")
    args = parser.parse_args()
    asyncio.run(serve(args))


if __name__ == "__main__":
    main()
