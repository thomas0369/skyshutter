"""Finding the camera and its control port on the camera's own access point.

When a Nikon camera opens its WiFi it is normally the gateway of the network
(192.168.1.1 on Coolpix models, 192.168.0.1 on some others).  Which service it
exposes is the open question this module helps answer.
"""

from __future__ import annotations

import socket
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

from .ptpip import DEFAULT_PORT, PtpIpConnection, PtpIpError

# Ports worth trying on a camera access point.  15740 is PTP/IP; the rest are
# services other vendors (and Nikon's own WMU/SnapBridge builds) have used.
KNOWN_PORTS: dict[int, str] = {
    21: "ftp",
    23: "telnet",
    80: "http",
    443: "https",
    554: "rtsp",
    5000: "upnp/http-alt",
    8080: "http-alt",
    8613: "canon-ccapi-style",
    15740: "ptp/ip",
    15741: "ptp/ip (alt)",
    15742: "ptp/ip (alt)",
    49152: "upnp",
    60152: "sony-style",
}

# Gateways seen on camera access points.
LIKELY_HOSTS = ("192.168.1.1", "192.168.0.1", "192.168.4.1", "10.0.0.1")


@dataclass
class ProbeResult:
    host: str
    open_ports: dict[int, str] = field(default_factory=dict)
    ptpip_reachable: bool = False
    responder_name: str = ""
    responder_guid: str = ""
    error: str = ""

    def summary(self) -> str:
        lines = [f"host {self.host}"]
        if self.open_ports:
            for port, name in sorted(self.open_ports.items()):
                lines.append(f"  open  {port:>6}  {name}")
        else:
            lines.append("  no open ports found")
        if self.ptpip_reachable:
            lines.append(f"  PTP/IP handshake OK: {self.responder_name} ({self.responder_guid})")
        elif self.error:
            lines.append(f"  PTP/IP handshake failed: {self.error}")
        return "\n".join(lines)


def is_port_open(host: str, port: int, timeout: float = 1.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def scan_ports(
    host: str,
    ports: list[int] | None = None,
    timeout: float = 1.0,
    workers: int = 32,
) -> dict[int, str]:
    targets = ports if ports is not None else sorted(KNOWN_PORTS)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        states = pool.map(lambda p: (p, is_port_open(host, p, timeout)), targets)
    return {port: KNOWN_PORTS.get(port, "unknown") for port, open_ in states if open_}


def probe(
    host: str,
    guid: uuid.UUID | None = None,
    name: str = "skyshutter",
    port: int = DEFAULT_PORT,
    timeout: float = 1.0,
    ports: list[int] | None = None,
) -> ProbeResult:
    """Port scan a camera and try a PTP/IP handshake against it."""
    result = ProbeResult(host=host, open_ports=scan_ports(host, ports, timeout))
    if port not in result.open_ports:
        result.error = f"port {port} closed"
        return result

    connection = PtpIpConnection(
        host, port=port, guid=guid, friendly_name=name, timeout=timeout + 4
    )
    try:
        connection.connect(with_events=False)
        result.ptpip_reachable = True
        result.responder_name = connection.responder_name
        result.responder_guid = str(connection.responder_guid)
    except (PtpIpError, OSError) as exc:
        result.error = str(exc)
    finally:
        connection.close()
    return result


def find_camera(hosts: tuple[str, ...] = LIKELY_HOSTS, timeout: float = 0.6) -> str | None:
    """Return the first host in ``hosts`` with an open PTP/IP port."""
    for host in hosts:
        if is_port_open(host, DEFAULT_PORT, timeout):
            return host
    return None
