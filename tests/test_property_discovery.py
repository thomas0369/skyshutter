"""Phase A: read-only property and storage inventory, against the simulator."""

from __future__ import annotations

import struct

from skyshutter.nikon import NikonCamera, NikonProperty
from skyshutter.ptp import (
    AccessCapability,
    DataType,
    FormFlag,
    PropertyDesc,
    StorageInfo,
)

# -- parser round-trips (no simulator) -------------------------------------


def test_property_desc_round_trips() -> None:
    desc = PropertyDesc(
        code=0x4001,
        data_type=DataType.UINT32,
        access=AccessCapability.GET_SET,
        form_flag=FormFlag.NONE,
        default_value=42,
        current_value=42,
    )
    assert PropertyDesc.parse(desc.pack()) == desc


def test_storage_info_round_trips() -> None:
    info = StorageInfo(
        storage_id=0x50000001,
        storage_type=0x0003,
        access_capability=0x0003,
        max_capacity=32 * 1024**3,
        free_space_bytes=28 * 1024**3,
        free_space_objects=12345,
    )
    assert StorageInfo.parse(info.pack()) == info


def test_code_list_parses_the_ptp_array_form() -> None:
    payload = struct.pack("<I", 2) + struct.pack("<H", 0x4001) + struct.pack("<H", 0x4002)
    assert NikonCamera._parse_code_list(payload) == [0x4001, 0x4002]


def test_code_list_falls_back_to_a_bare_run_of_uint16() -> None:
    payload = struct.pack("<H", 0x4001) + struct.pack("<H", 0x4002) + struct.pack("<H", 0x4003)
    assert NikonCamera._parse_code_list(payload) == [0x4001, 0x4002, 0x4003]


# -- against the simulator --------------------------------------------------


def test_vendor_property_codes_come_from_the_camera(camera_address: tuple[str, int]) -> None:
    host, port = camera_address
    with NikonCamera.open(host, port=port, timeout=5) as camera:
        codes = set(camera.vendor_property_codes())
    assert NikonProperty.LIVE_VIEW_STATUS in codes
    assert NikonProperty.REMAINING_CAPTURE in codes


def test_property_desc_reports_type_and_default(camera_address: tuple[str, int]) -> None:
    host, port = camera_address
    with NikonCamera.open(host, port=port, timeout=5) as camera:
        desc = camera.property_desc(NikonProperty.REMAINING_CAPTURE)
    assert desc.data_type == int(DataType.UINT32)
    assert desc.default_value == 999


def test_properties_maps_every_describable_code(camera_address: tuple[str, int]) -> None:
    host, port = camera_address
    with NikonCamera.open(host, port=port, timeout=5) as camera:
        props = camera.properties()
    # The simulator describes exactly the six vendor properties it holds; the
    # standard codes it advertises but does not describe are skipped.
    assert set(props) == {
        NikonProperty.LIVE_VIEW_STATUS,
        NikonProperty.LIVE_VIEW_PROHIBIT,
        NikonProperty.SHUTTER_SPEED,
        NikonProperty.REMAINING_CAPTURE,
        NikonProperty.LENS_FOCAL_MIN,
        NikonProperty.LENS_FOCAL_MAX,
    }
    assert all(isinstance(v, PropertyDesc) for v in props.values())


def test_storage_ids_and_info_agree(camera_address: tuple[str, int]) -> None:
    host, port = camera_address
    with NikonCamera.open(host, port=port, timeout=5) as camera:
        ids = camera.storage_ids()
        info = camera.storage_info(ids[0])
    assert ids == [0x50000001]
    assert info.storage_id == 0x50000001
    assert info.max_capacity == 32 * 1024**3


def test_write_property_value(camera_address: tuple[str, int]) -> None:
    host, port = camera_address
    with NikonCamera.open(host, port=port, timeout=5) as camera:
        # Shutter speed starts at 0 in the simulator
        assert camera.get_property_u32(NikonProperty.SHUTTER_SPEED) == 0
        camera.set_property_u32(NikonProperty.SHUTTER_SPEED, 42)
        assert camera.get_property_u32(NikonProperty.SHUTTER_SPEED) == 42
