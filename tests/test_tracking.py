"""Goto-pulse tracking against the physics MountSim.

The satellite is replaced by a linear az/alt ramp (0.6/0.25 deg/s — the
shape of an ISS pass near culmination). The tracker must keep both axes
within a fraction of a degree of the true position for the whole pass.
"""

from __future__ import annotations

import pytest

from skyshutter.mount import SynscanClient
from skyshutter.tracking import GotoPulseTracker, acquire
from test_mount import FakeClock, MountSim


@pytest.fixture()
def rig():
    clock = FakeClock(start=1_000_000.0)
    sim = MountSim(clock=clock)
    client = SynscanClient(host="127.0.0.1", port=sim.addr[1], timeout=2.0, allow_motion=True)
    yield clock, sim, client
    sim.close()


def _ramp(rise: float):
    """az 0.6 deg/s, alt 0.25 deg/s from ``rise`` — ISS-like pass shape."""

    def target(t: float) -> tuple[float, float]:
        dt = max(0.0, t - rise)
        return (100.0 + 0.6 * dt, 35.0 + 0.25 * dt)

    return target


def test_pulse_tracking_keeps_error_small(rig) -> None:
    clock, _sim, client = rig
    start = clock.now()
    rise = start + 100.0
    target = _ramp(rise)

    # acquisition: slew to the rise point (100 deg az away, ~57 s at 1.77 deg/s)
    assert acquire(client, target, rise, clock=clock, deadline_s=90.0)
    # wait for the pass to start (CLI does the same before tracking)
    clock.sleep(max(0.0, rise - clock.now()))

    tracker = GotoPulseTracker(client, pulse_s=1.0, clock=clock)
    report = tracker.track(target, end_time=rise + 60.0)

    assert report.pulses == 60
    assert report.max_error_deg < 0.35, f"max error {report.max_error_deg:.3f} deg too big"
    assert report.mean_error_deg < 0.15
    # both axes stopped at the end
    assert not client.axis_status(1).running
    assert not client.axis_status(2).running
    # and the mount ended near where the satellite is now
    az_now, alt_now = target(rise + 60.0)
    assert abs(client.position_degrees(1) - az_now) < 1.0
    assert abs(client.position_degrees(2) - alt_now) < 1.0


def test_pulse_tracking_interrupt_stops_axes(rig) -> None:
    clock, _sim, client = rig
    rise = clock.now()
    target = _ramp(rise)

    def exploding_target(t: float) -> tuple[float, float]:
        if t > rise + 5.0:
            raise KeyboardInterrupt
        return target(t)

    tracker = GotoPulseTracker(client, pulse_s=1.0, clock=clock)
    with pytest.raises(KeyboardInterrupt):
        tracker.track(exploding_target, end_time=rise + 60.0)
    assert not client.axis_status(1).running
    assert not client.axis_status(2).running


def test_acquisition_deadline_returns_false(rig) -> None:
    clock, _sim, client = rig
    start = clock.now()
    # 190 deg away but only 5 s patience: cannot get there in time
    far = lambda t: (190.0 + 0.6 * (t - start), 35.0)  # noqa: E731
    assert acquire(client, far, start + 150.0, clock=clock, deadline_s=5.0) is False
