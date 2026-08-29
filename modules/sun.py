"""Sunrise, sunset, and civil twilight — computed locally, no API.

The whole point of a Meshtastic bot is resilience when the network is
down. This module computes solar events from known coordinates using
the NOAA solar-position algorithm (Spencer/Fourier series), accurate
to well under a minute — more than enough for "when can I walk the
dog without a flashlight."
"""

import datetime as dt
import logging
import math
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

# Zenith angles for different solar events:
# Sunrise/sunset: 90.833° — top of the disc at the horizon, includes
#   standard atmospheric refraction (34 arcmin) and the solar radius
#   (16 arcmin).
# Civil twilight: 96° — sun 6° below the horizon. Enough light for
#   most outdoor activities without artificial lighting. This is what
#   hunters, anglers, and dog-walkers actually care about.
_ZENITH_RISE_SET = math.radians(90.0 + 50.0 / 60.0)  # 90.833°
_ZENITH_CIVIL = math.radians(96.0)                  # civil twilight


def _day_of_year(d):
    """1-indexed day of year (Jan 1 = 1)."""
    return d.timetuple().tm_yday


def _declination(n):
    """Solar declination in radians — Spencer/Fourier series (NOAA)."""
    gamma = 2.0 * math.pi * (n - 1) / 365.0
    return (
        0.006918
        - 0.399912 * math.cos(gamma)
        + 0.070257 * math.sin(gamma)
        - 0.006758 * math.cos(2.0 * gamma)
        + 0.000907 * math.sin(2.0 * gamma)
        - 0.002697 * math.cos(3.0 * gamma)
        + 0.00148 * math.sin(3.0 * gamma)
    )


def _equation_of_time(n):
    """Equation of time in minutes — Spencer/Fourier (NOAA)."""
    gamma = 2.0 * math.pi * (n - 1) / 365.0
    return 229.18 * (
        0.000075
        + 0.001868 * math.cos(gamma)
        - 0.032077 * math.sin(gamma)
        - 0.014615 * math.cos(2.0 * gamma)
        - 0.040849 * math.sin(2.0 * gamma)
    )


def _hour_angle(lat_rad, decl_rad, zenith_rad):
    """Hour angle in radians for a given zenith at the given latitude.
    Returns None when the sun never reaches that zenith (polar day/night).
    """
    cos_ha = (
        math.cos(zenith_rad)
        / (math.cos(lat_rad) * math.cos(decl_rad))
        - math.tan(lat_rad) * math.tan(decl_rad)
    )
    # Clamp to [-1, 1] to absorb floating-point drift near solstices
    # where the sun barely rises/sets.
    if cos_ha <= -1.0:
        return math.pi   # never sets (polar day)
    if cos_ha >= 1.0:
        return 0.0       # never rises (polar night)
    return math.acos(cos_ha)


def _minutes_to_time(minutes):
    """Convert minutes-since-midnight to (hour, minute)."""
    minutes %= 1440
    h = int(minutes // 60)
    m = int(minutes % 60)
    return h, m


class Sun:
    """Compute sunrise, sunset, and civil twilight for a location."""

    def __init__(self, lat, lon, tz="America/Chicago"):
        self.lat_rad = math.radians(lat)
        self.lon = lon
        self.tz = ZoneInfo(tz)

    # -- public --------------------------------------------------------

    def get_sun(self, now=None):
        """Return a compact multi-line sun summary for the mesh.

        Accepts an optional timezone-aware ``now`` for testing; defaults
        to the current instant in the configured timezone.
        """
        try:
            if now is None:
                now = dt.datetime.now(self.tz)
            elif now.tzinfo is None:
                now = now.replace(tzinfo=self.tz)

            d = now.date()
            n = _day_of_year(d)
            decl = _declination(n)
            eot = _equation_of_time(n)

            # Solar noon in minutes from midnight (local solar time).
            tz_offset_hours = now.utcoffset().total_seconds() / 3600.0
            tz_offset = tz_offset_hours * 60.0
            solar_noon_min = 720.0 - 4.0 * self.lon - eot + tz_offset

            ha_rise = _hour_angle(self.lat_rad, decl, _ZENITH_RISE_SET)
            ha_civil = _hour_angle(self.lat_rad, decl, _ZENITH_CIVIL)

            def _fmt(minutes):
                h, m = _minutes_to_time(minutes)
                return f"{h:02d}:{m:02d}"

            rise_min = solar_noon_min - math.degrees(ha_rise) * 4.0
            set_min = solar_noon_min + math.degrees(ha_rise) * 4.0
            dawn_min = solar_noon_min - math.degrees(ha_civil) * 4.0
            dusk_min = solar_noon_min + math.degrees(ha_civil) * 4.0

            date_str = d.strftime("%a %b %-d")
            return "\n".join([
                f"☀️  {date_str}",
                f"🌅 Sunrise       {_fmt(rise_min)}",
                f"🌇 Sunset        {_fmt(set_min)}",
                f"🌆 Dawn (civil)  {_fmt(dawn_min)}",
                f"🌃 Dusk (civil)  {_fmt(dusk_min)}",
            ])
        except Exception as e:
            logger.error("Failed to compute sun times: %s", e)
            return "Failed to compute sun times."
