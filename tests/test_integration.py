"""End to end tests against the bundled PTP/IP camera simulator."""

from __future__ import annotations

import pytest

from skyshutter.nikon import NikonCamera, NikonOperation
from skyshutter.ptp import PtpError, ResponseCode
from skyshutter.ptpip import PtpIpConnection
from skyshutter.simulator import SIMULATOR_GUID, SimulatorServer


def test_handshake_reports_the_responder_identity(camera_address: tuple[str, int]) -> None:
    host, port = camera_address
    with PtpIpConnection(host, port=port, timeout=5) as connection:
        assert connection.connection_number == 1
        assert connection.responder_name == "COOLPIX P1100"
        assert connection.responder_guid == SIMULATOR_GUID


def test_device_info_reaches_the_client(camera_address: tuple[str, int]) -> None:
    host, port = camera_address
    with NikonCamera.open(host, port=port, timeout=5) as camera:
        info = camera.device_info
        assert info is not None
        assert info.is_nikon
        assert "P1100" in info.model
        assert info.supports(NikonOperation.GET_LIVE_VIEW_IMG)


def test_capture_uses_the_vendor_opcode(
    camera_address: tuple[str, int], camera_server: SimulatorServer
) -> None:
    host, port = camera_address
    with NikonCamera.open(host, port=port, timeout=5) as camera:
        camera.capture()
        camera.capture()
    assert camera_server.captures == 2


def test_live_view_frames_are_carved_out_of_the_payload(
    camera_address: tuple[str, int], camera_server: SimulatorServer
) -> None:
    host, port = camera_address
    frames = []
    with NikonCamera.open(host, port=port, timeout=5) as camera:
        for frame in camera.stream_live_view(fps=0):
            frames.append(frame)
            assert camera_server.live_view_active
            if len(frames) == 3:
                break
    assert len(frames) == 3
    # leaving the loop must close the generator, which ends live view again
    assert all(f.startswith(b"\xff\xd8\xff") and f.endswith(b"\xff\xd9") for f in frames)
    assert not camera_server.live_view_active


def test_live_view_reports_busy_before_it_is_started(camera_address: tuple[str, int]) -> None:
    host, port = camera_address
    with NikonCamera.open(host, port=port, timeout=5) as camera:
        assert camera.get_live_view_frame() is None


def test_unsupported_operation_raises_with_the_response_code(
    camera_address: tuple[str, int],
) -> None:
    host, port = camera_address
    with NikonCamera.open(host, port=port, timeout=5) as camera:
        with pytest.raises(PtpError) as excinfo:
            camera.connection.transaction(NikonOperation.GET_VENDOR_PROP_CODES)
    assert excinfo.value.code == ResponseCode.OPERATION_NOT_SUPPORTED


def test_transaction_ids_increment(camera_address: tuple[str, int]) -> None:
    host, port = camera_address
    with PtpIpConnection(host, port=port, timeout=5) as connection:
        connection.open_session()
        before = connection._transaction_id
        connection.transaction(0x1001)
        assert connection._transaction_id == before + 1
