"""Tests for the sun module (pure Python, no API)."""

import datetime as dt
import unittest

from modules.sun import Sun


def _ct(y, m, d, hh=0, mm=0):
    """Build a Central-time datetime for test injection."""
    from zoneinfo import ZoneInfo
    return dt.datetime(y, m, d, hh, mm, 0, tzinfo=ZoneInfo("America/Chicago"))


def _find_line(output, keyword):
    """Extract the time from a sun output line like '🌅 Sunrise       06:25'."""
    for line in output.split("\n"):
        if keyword in line:
            return line.split()[-1]
    raise AssertionError(f"'{keyword}' not found in output")


def _mins(timestr):
    """Convert 'HH:MM' to minutes since midnight."""
    h, m = map(int, timestr.split(":"))
    return h * 60 + m


class TestSunOutput(unittest.TestCase):
    """Test the public get_sun() method — Mobile, AL coordinates."""

    LAT, LON = 30.6954, -88.0399

    def test_output_has_five_lines(self):
        s = Sun(self.LAT, self.LON)
        out = s.get_sun(_ct(2026, 8, 28, 12, 0))
        lines = out.split("\n")
        self.assertEqual(len(lines), 5)

    def test_sunrise_before_sunset(self):
        s = Sun(self.LAT, self.LON)
        out = s.get_sun(_ct(2026, 8, 28, 12, 0))
        self.assertLess(_find_line(out, "Sunrise"), _find_line(out, "Sunset"))

    def test_civil_twilight_books_sunrise_sunset(self):
        s = Sun(self.LAT, self.LON)
        out = s.get_sun(_ct(2026, 8, 28, 12, 0))
        dawn = _find_line(out, "Dawn")
        sr = _find_line(out, "Sunrise")
        ss = _find_line(out, "Sunset")
        dusk = _find_line(out, "Dusk")
        self.assertLess(dawn, sr)
        self.assertLess(sr, ss)
        self.assertLess(ss, dusk)

    def test_known_august_sunrise(self):
        """Aug 28 Mobile AL: sunrise ~6:23 am (+/- 3 min)."""
        s = Sun(self.LAT, self.LON)
        out = s.get_sun(_ct(2026, 8, 28, 12, 0))
        m = _mins(_find_line(out, "Sunrise"))
        self.assertTrue(380 <= m <= 386,
                        f"sunrise {_find_line(out, 'Sunrise')} outside range")

    def test_known_august_sunset(self):
        """Aug 28 Mobile AL: sunset ~7:22 pm CDT (+/- 3 min)."""
        s = Sun(self.LAT, self.LON)
        out = s.get_sun(_ct(2026, 8, 28, 12, 0))
        m = _mins(_find_line(out, "Sunset"))
        self.assertTrue(1159 <= m <= 1165,
                        f"sunset {_find_line(out, 'Sunset')} outside range")

    def test_date_line_shows_weekday(self):
        s = Sun(self.LAT, self.LON)
        out = s.get_sun(_ct(2026, 8, 28, 12, 0))
        self.assertIn("Fri Aug 28", out)

    def test_now_defaults_to_current_time(self):
        s = Sun(self.LAT, self.LON)
        out = s.get_sun()
        self.assertIn("Sunrise", out)
        self.assertIn("Sunset", out)

    def test_civil_twilight_always_exists_for_mobile(self):
        s = Sun(self.LAT, self.LON)
        for dt_val in [_ct(2026, 6, 21, 12, 0),
                       _ct(2026, 12, 21, 12, 0),
                       _ct(2026, 3, 20, 12, 0)]:
            out = s.get_sun(dt_val)
            self.assertIn("Dawn", out, f"missing dawn on {dt_val}")
            self.assertIn("Dusk", out, f"missing dusk on {dt_val}")

    def test_winter_days_are_shorter(self):
        s = Sun(self.LAT, self.LON)
        summer = s.get_sun(_ct(2026, 6, 21, 12, 0))
        winter = s.get_sun(_ct(2026, 12, 21, 12, 0))

        summer_sr = _mins(_find_line(summer, "Sunrise"))
        winter_sr = _mins(_find_line(winter, "Sunrise"))
        summer_ss = _mins(_find_line(summer, "Sunset"))
        winter_ss = _mins(_find_line(winter, "Sunset"))

        self.assertLess(summer_sr, winter_sr,
                        "summer sunrise should be earlier")
        self.assertGreater(summer_ss, winter_ss,
                           "summer sunset should be later")


if __name__ == "__main__":
    unittest.main()
