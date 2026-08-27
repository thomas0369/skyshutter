"""Satellite tracking: TLE -> SGP4 -> topocentric az/alt.

The heavy lifting (SGP4 propagation) is delegated to the optional ``sgp4``
package (Vallado reference port, MIT) — imported lazily so the rest of
skyshutter stays stdlib-only.  Install with ``pip install sgp4``.

Everything else — GMST, the TEME->SEZ rotation, pass search — is plain
math implemented here (Vallado, *Fundamentals of Astrodynamics*, §3.3).

Azimuth is degrees from north, clockwise; altitude degrees above horizon.
"""

from __future__ import annotations

import math
import time
import urllib.request
from dataclasses import dataclass

CELESTRAK_URL = "https://celestrak.org/NORAD/elements/gp.php?CATNR={norad}&FORMAT=TLE"
#: passes below this altitude are treated as invisible
EARTH_RADIUS_KM = 6378.137
MIN_ALT_DEG = 10.0


@dataclass(frozen=True)
class Observer:
    lat_deg: float
    lon_deg: float
    elevation_m: float = 0.0


@dataclass(frozen=True)
class SkyPosition:
    unix_time: float
    az_deg: float
    alt_deg: float
    range_km: float
    #: line-of-sight rate in km/s (negative = approaching)
    range_rate_kms: float = 0.0


def unix_to_jd(unix: float) -> tuple[float, float]:
    """Split a unix timestamp into (julian day, fraction <= 1.0)."""
    jd_full = unix / 86400.0 + 2440587.5
    jd = math.floor(jd_full - 0.5) + 0.5
    return jd, jd_full - jd


def gmst_deg(unix: float) -> float:
    """Greenwich mean sidereal time (Vallado eq. 3-40).

    Uses the *full* julian date including the fraction of day — the
    formula would otherwise only step once per UT day.
    """
    jd_full = unix / 86400.0 + 2440587.5
    t = (jd_full - 2451545.0) / 36525.0
    gmst = (
        280.46061837
        + 360.98564736629 * (jd_full - 2451545.0)
        + 0.000387933 * t * t
        - t * t * t / 38710000.0
    )
    return gmst % 360.0


def observer_teme(observer: Observer, unix: float) -> tuple[float, float, float]:
    """Observer position in TEME (spherical earth — geocentric latitude,
    good to ~0.2 deg for a 6378 km sphere; fine for pointing a mount)."""
    lat = math.radians(observer.lat_deg)
    lon = math.radians(observer.lon_deg)
    g = math.radians(gmst_deg(unix))
    radius = EARTH_RADIUS_KM + observer.elevation_m / 1000.0
    x_e = radius * math.cos(lat) * math.cos(lon)
    y_e = radius * math.cos(lat) * math.sin(lon)
    z_e = radius * math.sin(lat)
    # ECEF -> TEME undoes the earth rotation: r_teme = ROT3(gmst)^T r_ecef
    x_t = math.cos(g) * x_e - math.sin(g) * y_e
    y_t = math.sin(g) * x_e + math.cos(g) * y_e
    return x_t, y_t, z_e


def teme_to_sez(
    r_teme: tuple[float, float, float], lat_deg: float, lon_deg: float, unix: float
) -> tuple[float, float, float]:
    """Rotate a TEME position into south/east/zenith at the observer."""
    lat = math.radians(lat_deg)
    theta = math.radians(gmst_deg(unix) + lon_deg)
    sin_lat, cos_lat = math.sin(lat), math.cos(lat)
    sin_t, cos_t = math.sin(theta), math.cos(theta)
    x, y, z = r_teme
    south = sin_lat * cos_t * x + sin_lat * sin_t * y - cos_lat * z
    east = -sin_t * x + cos_t * y
    zenith = cos_lat * cos_t * x + cos_lat * sin_t * y + sin_lat * z
    return south, east, zenith


def sez_to_az_alt_deg(south: float, east: float, zenith: float) -> tuple[float, float]:
    """Azimuth compass-style (N=0, E=90) and altitude above the horizon."""
    r = math.sqrt(south * south + east * east + zenith * zenith)
    alt = math.degrees(math.asin(max(-1.0, min(1.0, zenith / r))))
    az = math.degrees(math.atan2(east, -south)) % 360.0
    return az, alt


def angle_diff_deg(a: float, b: float) -> float:
    """Smallest signed difference b-a wrapped to (-180, 180]."""
    return (b - a + 180.0) % 360.0 - 180.0


class Satellite:
    """One satellite built from a TLE pair."""

    def __init__(self, line1: str, line2: str) -> None:
        try:
            from sgp4.api import Satrec
        except ImportError as exc:  # pragma: no cover - depends on env
            raise RuntimeError(
                "satellite tracking needs the optional 'sgp4' package (pip install sgp4)"
            ) from exc
        self.name = "SAT"
        self.sat = Satrec.twoline2rv(line1.strip(), line2.strip())

    @classmethod
    def from_tle_text(cls, text: str) -> Satellite:
        """Build from classic three-line TLE text (name + 2 lines)."""
        lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
        if len(lines) >= 3 and not lines[0].startswith("1 "):
            sat = cls(lines[1], lines[2])
            sat.name = lines[0]
            return sat
        if len(lines) < 2:
            raise ValueError("TLE text needs at least the two element lines")
        return cls(lines[-2], lines[-1])
        sat = cls(lines[0], lines[1])
        return sat

    @classmethod
    def from_file(cls, path: str) -> Satellite:
        with open(path, encoding="ascii") as handle:
            return cls.from_tle_text(handle.read())

    @classmethod
    def from_norad_id(cls, norad_id: int, timeout: float = 15.0) -> Satellite:
        url = CELESTRAK_URL.format(norad=norad_id)
        with urllib.request.urlopen(url, timeout=timeout) as response:
            text = response.read().decode("ascii")
        if "1 " not in text:
            raise ValueError(f"celestrak returned no TLE for {norad_id}: {text[:120]!r}")
        return cls.from_tle_text(text)

    def position(self, observer: Observer, unix: float) -> SkyPosition:
        """Topocentric position at a unix timestamp."""
        jd, frac = unix_to_jd(unix)
        _e, r, v = self.sat.sgp4(jd, frac)
        if r is None:
            raise RuntimeError(f"sgp4 propagation failed at {unix}: {_e}")
        ox, oy, oz = observer_teme(observer, unix)
        r_topo = (r[0] - ox, r[1] - oy, r[2] - oz)
        south, east, zenith = teme_to_sez(r_topo, observer.lat_deg, observer.lon_deg, unix)
        az, alt = sez_to_az_alt_deg(south, east, zenith)
        range_km = math.sqrt(south * south + east * east + zenith * zenith)
        # line-of-sight rate: project velocity (observer rotation neglected)
        vs, ve, vz = teme_to_sez(v, observer.lat_deg, observer.lon_deg, unix)
        range_rate = (south * vs + east * ve + zenith * vz) / range_km
        return SkyPosition(unix, az, alt, range_km, range_rate)

    def track_rates(self, observer: Observer, unix: float) -> tuple[SkyPosition, float, float]:
        """Position plus az/alt rates in deg/s one second ahead."""
        now = self.position(observer, unix)
        nxt = self.position(observer, unix + 1.0)
        return now, angle_diff_deg(now.az_deg, nxt.az_deg), nxt.alt_deg - now.alt_deg

    def next_passes(
        self, observer: Observer, hours: float = 12.0, min_alt: float = MIN_ALT_DEG
    ) -> list[tuple[float, float, float]]:
        """Visible passes within `hours`: list of (rise, peak, set) unix times.

        Coarse 20 s scan (satellites move up to ~1.5 deg/s at zenith passes;
        20 s keeps the altitude error below ~1.5 deg for the boundary).
        """
        start = time.time()
        step = 20.0
        passes: list[tuple[float, float, float]] = []
        ascending = False
        rise = peak = peak_alt = 0.0
        t = start
        end = start + hours * 3600.0
        while t <= end:
            alt = self.position(observer, t).alt_deg
            if not ascending and alt > min_alt:
                ascending = True
                rise, peak, peak_alt = t, t, alt
            elif ascending:
                if alt > peak_alt:
                    peak, peak_alt = t, alt
                if alt <= min_alt:
                    passes.append((rise, peak, t))
                    ascending = False
            t += step
        if ascending:  # pass still ongoing at the horizon of the search
            passes.append((rise, peak, end))
        return passes
