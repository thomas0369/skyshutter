"""Goto-pulse satellite tracking for the AZ-GTi.

The AZ-GTi firmware ignores :I (step period) — slew speeds are fixed at
2.07 deg/s (slow) / 1.57 deg/s (fast), measured 2026-08-27. Continuous
rate-based tracking is therefore impossible. This module follows a moving
target by re-issuing small goto targets (:S + :J, ~1.77 deg/s goto rate)
every pulse — the mount hops along the predicted track like a staircase.

The tracker is transport-agnostic: it only needs a SynscanClient-like
object and a time source (injectable for tests, see tests/test_mount.py
FakeClock).
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Protocol

from .mount import AXIS_ALT, AXIS_AZ, SynscanClient


class Clock(Protocol):
    def now(self) -> float: ...

    def sleep(self, seconds: float) -> None: ...


class RealClock:
    def now(self) -> float:
        return time.time()

    def sleep(self, seconds: float) -> None:
        time.sleep(seconds)


TargetFunction = Callable[[float], tuple[float, float]]
"""Maps unix time -> (az_deg, alt_deg) of the object to follow."""


@dataclass
class TrackReport:
    pulses: int = 0
    max_error_deg: float = 0.0
    mean_error_deg: float = 0.0
    errors: list[float] = field(default_factory=list)

    def note(self, error_deg: float) -> None:
        self.errors.append(error_deg)
        self.max_error_deg = max(self.max_error_deg, error_deg)
        self.mean_error_deg = sum(self.errors) / len(self.errors)


class GotoPulseTracker:
    """Follow ``target_func`` by pulsing small gotos every ``pulse_s``.

    Every pulse sends the mount to where the target will be ``lead_s``
    seconds from now (default: one full pulse — the goto spends the whole
    pulse covering the intra-pulse distance, keeping the axes moving).
    Errors are measured against the true target position each pulse.
    """

    def __init__(
        self,
        client: SynscanClient,
        *,
        pulse_s: float = 1.0,
        lead_s: float | None = None,
        clock: Clock | None = None,
        announce: Callable[[str], None] | None = None,
    ) -> None:
        self._client = client
        self._pulse_s = pulse_s
        # one full pulse of lead: the goto needs the pulse duration to cover
        # the intra-pulse distance, so the mount keeps moving instead of
        # stopping mid-pulse (measured goto rate 1.77 deg/s > LEO rates)
        self._lead_s = pulse_s if lead_s is None else lead_s
        self._clock = clock or RealClock()
        self._announce = announce or (lambda _msg: None)

    def track(self, target_func: TargetFunction, end_time: float) -> TrackReport:
        """Pulse until ``end_time`` (unix). Stops both axes on exit."""
        report = TrackReport()
        try:
            while self._clock.now() < end_time:
                az, alt = target_func(self._clock.now() + self._lead_s)
                self._client.goto_degrees(AXIS_AZ, az)
                self._client.goto_degrees(AXIS_ALT, alt)
                self._clock.sleep(self._pulse_s)
                true_az, true_alt = target_func(self._clock.now())
                cur_az = self._client.position_degrees(AXIS_AZ)
                cur_alt = self._client.position_degrees(AXIS_ALT)
                d_az = abs((cur_az - true_az + 180.0) % 360.0 - 180.0)
                error = max(d_az, abs(cur_alt - true_alt))
                report.note(error)
                report.pulses += 1
                self._announce(
                    f"pulse {report.pulses}: az={cur_az:7.2f} alt={cur_alt:6.2f} "
                    f"err={error:5.2f} deg"
                )
        except KeyboardInterrupt:
            self._client.stop_all()
            raise
        self._client.stop_all()
        return report


def acquire(
    client: SynscanClient,
    target_func: TargetFunction,
    ready_time: float,
    *,
    tolerance_deg: float = 0.5,
    deadline_s: float = 90.0,
    clock: Clock | None = None,
) -> bool:
    """Goto the target position at ``ready_time`` and wait until settled.

    Returns True when within ``tolerance_deg`` on both axes (or already
    past ready_time), False when the deadline expired.
    """
    clock = clock or RealClock()
    az, alt = target_func(ready_time)
    client.goto_degrees(AXIS_AZ, az)
    client.goto_degrees(AXIS_ALT, alt)
    deadline = clock.now() + deadline_s
    while clock.now() < deadline:
        d_az = abs((client.position_degrees(AXIS_AZ) - az + 180.0) % 360.0 - 180.0)
        d_alt = abs(client.position_degrees(AXIS_ALT) - alt)
        if max(d_az, d_alt) < tolerance_deg:
            return True
        clock.sleep(1.0)
    return False
