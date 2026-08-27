"""Moon phase — computed locally, no API, no network.

The whole point of a Meshtastic bot is resilience when the network is
down, so lunar phase should not depend on an API call. This module
computes the current phase, illumination, and the dates of the next
full and new moons from a known-new-moon epoch and the mean synodic
month. Accurate to well under a day — more than enough for "what's the
moon doing tonight."
"""

import datetime as dt
import logging
import math
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

# Mean synodic (lunar) month in days.
SYNODIC_MONTH = 29.530588853

# A known new moon: 2000-01-06 18:14 UTC. Age is measured forward from
# this instant modulo SYNODIC_MONTH.
_KNOWN_NEW_MOON = dt.datetime(2000, 1, 6, 18, 14, 0,
                              tzinfo=dt.timezone.utc)

# The eight principal phases, indexed by integer eighth of the cycle
# (0 = new, 2 = first quarter, 4 = full, 6 = last quarter).
_PHASES = [
    ("New Moon", "🌑"),
    ("Waxing Crescent", "🌒"),
    ("First Quarter", "🌓"),
    ("Waxing Gibbous", "🌔"),
    ("Full Moon", "🌕"),
    ("Waning Gibbous", "🌖"),
    ("Last Quarter", "🌗"),
    ("Waning Crescent", "🌘"),
]


class Moon:
    """Compute current lunar phase and upcoming full/new moons."""

    def __init__(self, tz="America/Chicago"):
        self.tz = ZoneInfo(tz)

    # -- core math (static, pure) -----------------------------------

    @staticmethod
    def _age_days(now):
        """Age of the moon in days since the last new moon (0–29.53)."""
        seconds = (now - _KNOWN_NEW_MOON).total_seconds()
        return (seconds / 86400.0) % SYNODIC_MONTH

    @staticmethod
    def _illumination(age):
        """Fraction of the disc illuminated (0 = new, 1 = full)."""
        return (1.0 - math.cos(2.0 * math.pi * age / SYNODIC_MONTH)) / 2.0

    @staticmethod
    def _phase(age):
        """Return (name, emoji) for a given age in days."""
        fraction = age / SYNODIC_MONTH
        idx = int(fraction * 8 + 0.5) % 8
        return _PHASES[idx]

    @staticmethod
    def _next_event_days(age, target_age):
        """Days until the moon reaches target_age, wrapping forward."""
        days = (target_age - age) % SYNODIC_MONTH
        # If the event is effectively "right now" (within an hour),
        # roll to the following cycle so we report the *next* one.
        if days < 1.0 / 24.0:
            days += SYNODIC_MONTH
        return days

    # -- public ------------------------------------------------------

    def get_moon(self, now=None):
        """Return a compact multi-line moon summary for the mesh.

        Accepts an optional timezone-aware `now` for testing; defaults
        to the current instant in UTC.
        """
        try:
            if now is None:
                now = dt.datetime.now(dt.timezone.utc)
            elif now.tzinfo is None:
                now = now.replace(tzinfo=dt.timezone.utc)

            age = self._age_days(now)
            illum = self._illumination(age)
            name, emoji = self._phase(age)

            # New moon at age 0; full moon at half the cycle.
            next_new_days = self._next_event_days(age, 0.0)
            next_full_days = self._next_event_days(age, SYNODIC_MONTH / 2.0)

            next_new = now + dt.timedelta(days=next_new_days)
            next_full = now + dt.timedelta(days=next_full_days)

            # Report dates in the local (Central) wall-clock timezone.
            new_ct = next_new.astimezone(self.tz)
            full_ct = next_full.astimezone(self.tz)

            return "\n".join([
                f"{emoji} {name} · {round(illum * 100)}% illuminated",
                f"Next 🌑: {new_ct.strftime('%a %b %-d')}",
                f"Next 🌕: {full_ct.strftime('%a %b %-d')}",
            ])
        except Exception as e:
            logger.error("Failed to compute moon phase: %s", e)
            return "Failed to compute moon phase."
