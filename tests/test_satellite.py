"""Tests for satellite math and the optional SGP4 integration.

The geometry tests are stdlib-only.  Tests touching SGP4 skip cleanly when
the optional package is missing (CI machines without it stay green).
"""

from __future__ import annotations

import time

import pytest

from skyshutter.satellite import (
    Observer,
    Satellite,
    angle_diff_deg,
    gmst_deg,
    sez_to_az_alt_deg,
    teme_to_sez,
    unix_to_jd,
)

sgp4 = pytest.importorskip("sgp4.api", reason="optional SGP4 engine not installed")

# Real ISS element set fetched from celestrak (epoche 26239 = 27.08.2026).
# Old TLEs stay formally propagatable — tests only assert plausibility.
ISS_TLE = (
    "1 25544U 98067A   26239.14379413  .00008717  00000+0  16243-3 0  9995",
    "2 25544  51.6326 308.8886 0007697  87.8986 272.2885 15.49649978582754",
)


def test_unix_to_jd_epoch() -> None:
    jd, frac = unix_to_jd(0.0)
    assert abs(jd + frac - 2440587.5) < 1e-9


def test_gmst_advances_one_sidereal_rotation_per_day() -> None:
    unix = 1_700_000_000.0
    sidereal_day = 86164.0905
    delta = (gmst_deg(unix + sidereal_day) - gmst_deg(unix)) % 360.0
    # exactly one earth rotation: wraps to 0 (or just below 360)
    assert delta < 0.05 or delta > 359.95


def test_teme_to_sez_zenith_at_north_pole() -> None:
    # any TEME vector along the rotation axis is straight up at the pole
    unix = 1_700_000_000.0
    south, east, zenith = teme_to_sez((0.0, 0.0, 7000.0), 90.0, 0.0, unix)
    assert abs(zenith - 7000.0) < 1e-6
    assert abs(south) < 1e-6 and abs(east) < 1e-6
    _az, alt = sez_to_az_alt_deg(south, east, zenith)
    assert abs(alt - 90.0) < 1e-9


def test_sez_azimuth_cardinals() -> None:
    az, alt = sez_to_az_alt_deg(-1.0, 0.0, 0.0)  # pointing north
    assert az == pytest.approx(0.0) and alt == pytest.approx(0.0)
    az, _ = sez_to_az_alt_deg(1.0, 0.0, 0.0)  # south
    assert az == pytest.approx(180.0)
    az, _ = sez_to_az_alt_deg(0.0, 1.0, 0.0)  # east
    assert az == pytest.approx(90.0)
    az, _ = sez_to_az_alt_deg(0.0, -1.0, 0.0)  # west
    assert az == pytest.approx(270.0)


def test_angle_diff_wraps() -> None:
    assert angle_diff_deg(350.0, 10.0) == pytest.approx(20.0)
    assert angle_diff_deg(10.0, 350.0) == pytest.approx(-20.0)
    assert angle_diff_deg(180.0, 180.0) == pytest.approx(0.0)


def test_observer_zenith_consistency() -> None:
    """A point straight above the observer must land at alt=90 for any
    lon/time — pins the ECEF->TEME rotation direction against teme_to_sez."""
    from skyshutter.satellite import observer_teme

    unix = 1_700_000_123.0
    for lat, lon in ((50.0, 8.68), (-33.0, 151.0), (0.0, -45.0)):
        observer = Observer(lat, lon)
        ox, oy, oz = observer_teme(observer, unix)
        r_up = (1.5 * ox, 1.5 * oy, 1.5 * oz)
        south, east, zenith = teme_to_sez(r_up, lat, lon, unix)
        _az, alt = sez_to_az_alt_deg(south, east, zenith)
        assert alt == pytest.approx(90.0, abs=1e-6)


def test_satellite_from_tle_and_orbit_radius() -> None:
    sat = Satellite(ISS_TLE[0], ISS_TLE[1])
    observer = Observer(50.0, 10.0)
    pos = sat.position(observer, time.time())
    # topocentric slant range: ~350 km overhead; on the far side of earth
    # (satellite below horizon) up to geocentric+earth-radius ~13,200 km
    assert 350.0 <= pos.range_km <= 13200.0
    assert 0.0 <= pos.az_deg < 360.0
    assert -90.0 <= pos.alt_deg <= 90.0


def test_track_rates_are_small_for_leo() -> None:
    sat = Satellite(ISS_TLE[0], ISS_TLE[1])
    observer = Observer(50.0, 10.0)
    _pos, daz, dalt = sat.track_rates(observer, time.time())
    assert abs(daz) < 2.0 and abs(dalt) < 2.0  # deg/s, LEO worst case ~1.5


def test_next_passes_finds_iss_over_24h() -> None:
    sat = Satellite(ISS_TLE[0], ISS_TLE[1])
    observer = Observer(50.0, 10.0)
    passes = sat.next_passes(observer, hours=24.0)
    assert passes, "ISS (51.6 deg inclination) must produce a >10 deg pass within 24 h"
    for rise, peak, settle in passes:
        assert rise <= peak <= settle
        # a visible ISS pass never lasts longer than ~12 min; 900 s is generous
        assert settle - rise < 900.0, f"pass too long: {settle - rise} s"


def test_satellite_missing_tle_text_raises() -> None:
    with pytest.raises(ValueError):
        Satellite.from_tle_text("nonsense")
