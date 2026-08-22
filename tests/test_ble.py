"""Pins the measured BLE GATT database of the camera.

These tests exist to make the measurement of 22.08.2026 hard to lose. They
assert the numbers a later capture would have to contradict — not behaviour of
our own code. If a future measurement disagrees, the table changes and these
tests change with it; silent drift is what they are here to prevent.
"""

from __future__ import annotations

import pytest

from skyshutter import ble
from skyshutter.ble import CHARACTERISTICS, Property

# --- the service ------------------------------------------------------------


def test_the_vendor_service_spans_the_measured_handle_range():
    assert ble.SERVICE_UUID16 == 0xDE00
    assert (ble.SERVICE_HANDLE, ble.SERVICE_END_HANDLE) == (0x0029, 0x0051)


def test_uuids_are_rendered_on_the_vendor_base_not_the_bluetooth_one():
    assert ble.characteristic(0x2000).uuid == "00002000-3dd4-4255-8d62-6dc7b9bd5561"
    assert not ble.VENDOR_UUID_BASE.endswith("00805f9b34fb")


def test_the_battery_level_lookalike_is_a_vendor_characteristic():
    """0x2a19 on the vendor base is not the SIG's Battery Level."""
    assert ble.characteristic(0x2A19).uuid.endswith(ble.VENDOR_UUID_BASE)


# --- the table itself -------------------------------------------------------


def test_eighteen_characteristics_were_seen():
    assert len(CHARACTERISTICS) == 18


def test_every_characteristic_lies_inside_the_service():
    for c in CHARACTERISTICS:
        assert ble.SERVICE_HANDLE < c.declaration_handle < ble.SERVICE_END_HANDLE
        assert c.value_handle <= ble.SERVICE_END_HANDLE


def test_handles_are_unique_and_ascending():
    handles = [h for c in CHARACTERISTICS for h in (c.declaration_handle, c.value_handle)]
    assert handles == sorted(handles)
    assert len(set(handles)) == len(handles)


def test_the_gaps_in_the_handle_range_are_exactly_the_notifying_characteristics():
    """Four handles are unaccounted for, and four characteristics can notify."""
    used = {h for c in CHARACTERISTICS for h in (c.declaration_handle, c.value_handle)}
    span = set(range(ble.SERVICE_HANDLE + 1, ble.SERVICE_END_HANDLE + 1))
    gaps = span - used

    notifying = ble.with_property(Property.NOTIFY) + ble.with_property(Property.INDICATE)
    assert gaps == {c.cccd_handle for c in notifying}
    assert gaps == {0x002C, 0x003D, 0x004C, 0x0051}


@pytest.mark.parametrize(
    ("uuid16", "declaration", "value", "properties"),
    [
        (0x2000, 0x002A, 0x002B, 0x2A),
        (0x2002, 0x002F, 0x0030, 0x08),
        (0x2008, 0x003B, 0x003C, 0x1A),
        (0x2A19, 0x0040, 0x0041, 0x02),
        (0x2087, 0x004F, 0x0050, 0x2A),
    ],
)
def test_spot_checks_against_the_log(uuid16, declaration, value, properties):
    c = ble.characteristic(uuid16)
    assert (c.declaration_handle, c.value_handle, int(c.properties)) == (
        declaration,
        value,
        properties,
    )


def test_the_characteristics_absent_from_the_range_stay_absent():
    for missing in (0x200A, 0x2081, 0x2085):
        with pytest.raises(KeyError):
            ble.characteristic(missing)


# --- properties -------------------------------------------------------------


def test_write_only_characteristics_carry_no_read_bit():
    for uuid16 in (0x2002, 0x2007, 0x2083):
        c = ble.characteristic(uuid16)
        assert c.can(Property.WRITE)
        assert not c.can(Property.READ)


def test_only_one_characteristic_notifies_the_rest_indicate():
    assert [c.uuid16 for c in ble.with_property(Property.NOTIFY)] == [0x2008]
    assert [c.uuid16 for c in ble.with_property(Property.INDICATE)] == [
        0x2000,
        0x2084,
        0x2087,
    ]


def test_a_read_only_characteristic_has_no_cccd():
    assert ble.characteristic(0x2003).cccd_handle is None


# --- lookups ----------------------------------------------------------------


def test_a_captured_handle_can_be_named():
    assert ble.by_value_handle(0x003C).uuid16 == 0x2008


def test_a_declaration_handle_is_not_a_value_handle():
    assert ble.by_value_handle(0x003B) is None


def test_an_unknown_handle_names_nothing():
    assert ble.by_value_handle(0x0100) is None
