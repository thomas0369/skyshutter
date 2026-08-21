from __future__ import annotations

import threading
from collections.abc import Iterator

import pytest

from skyshutter.simulator import SimulatorServer


@pytest.fixture
def camera_server() -> Iterator[SimulatorServer]:
    """A fake PTP/IP camera on an ephemeral loopback port."""
    server = SimulatorServer("127.0.0.1", 0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


@pytest.fixture
def camera_address(camera_server: SimulatorServer) -> tuple[str, int]:
    host, port = camera_server.server_address[:2]
    return str(host), int(port)
