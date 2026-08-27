"""Tests for the moon phase module (pure Python, no API)."""

import datetime as dt
import unittest

from modules.moon import SYNODIC_MONTH, Moon, _KNOWN_NEW_MOON


def _utc(y, m, d, hh=0, mm=0, ss=0):
    return dt.datetime(y, m, d, hh, mm, ss, tzinfo=dt.timezone.utc)


class TestMoonPhaseMath(unittest.TestCase):
    """Test the pure math behind _age_days / _illumination / _phase."""

    def test_age_zero_at_known_new_moon(self):
        self.assertAlmostEqual(Moon._age_days(_KNOWN_NEW_MOON), 0.0, places=4)

    def test_illumination_new_moon_is_zero(self):
        self.assertAlmostEqual(Moon._illumination(0.0), 0.0, places=3)

    def test_illumination_full_moon_is_one(self):
        self.assertAlmostEqual(
            Moon._illumination(SYNODIC_MONTH / 2), 1.0, places=3
        )

    def test_phase_name_at_principal_phases(self):
        # age 0 -> new, SYNODIC/4 -> first quarter, SYNODIC/2 -> full,
        # 3*SYNODIC/4 -> last quarter.
        self.assertEqual(Moon._phase(0.0)[0], "New Moon")
        self.assertEqual(Moon._phase(SYNODIC_MONTH / 4)[0], "First Quarter")
        self.assertEqual(Moon._phase(SYNODIC_MONTH / 2)[0], "Full Moon")
        self.assertEqual(
            Moon._phase(3 * SYNODIC_MONTH / 4)[0], "Last Quarter"
        )

    def test_phase_wraps_at_end_of_cycle(self):
        # Just before a full cycle completes is still "New Moon" territory
        # (the phase list wraps via modulo).
        age = SYNODIC_MONTH - 0.1
        self.assertEqual(Moon._phase(age)[0], "New Moon")

    def test_phase_emoji_attached(self):
        name, emoji = Moon._phase(SYNODIC_MONTH / 2)
        self.assertEqual(emoji, "🌕")


class TestNextEvent(unittest.TestCase):
    """Test _next_event_days forward-wrapping."""

    def test_next_full_from_quarter(self):
        # A quarter-cycle before full -> next full in ~quarter cycle.
        age = SYNODIC_MONTH / 4
        days = Moon._next_event_days(age, SYNODIC_MONTH / 2)
        self.assertAlmostEqual(days, SYNODIC_MONTH / 4, places=3)

    def test_next_new_from_full(self):
        # At full moon, next new moon is half a cycle away.
        age = SYNODIC_MONTH / 2
        days = Moon._next_event_days(age, 0.0)
        self.assertAlmostEqual(days, SYNODIC_MONTH / 2, places=3)

    def test_event_right_now_rolls_forward(self):
        # At the exact new-moon instant, "next new moon" should be a full
        # cycle away, not zero.
        days = Moon._next_event_days(0.0, 0.0)
        self.assertGreater(days, SYNODIC_MONTH - 1.0)
        self.assertLess(days, SYNODIC_MONTH + 1.0)


class TestGetMoon(unittest.TestCase):
    """Test the public get_moon() output."""

    def test_output_contains_phase_and_illumination(self):
        m = Moon()
        out = m.get_moon(_KNOWN_NEW_MOON)
        self.assertIn("New Moon", out)
        self.assertIn("0% illuminated", out)

    def test_output_lists_next_new_and_full(self):
        m = Moon()
        out = m.get_moon(_KNOWN_NEW_MOON)
        self.assertIn("Next 🌑:", out)
        self.assertIn("Next 🌕:", out)

    def test_naive_datetime_assumed_utc(self):
        # A naive datetime must not crash — it is assumed UTC.
        m = Moon()
        naive = dt.datetime(2026, 8, 26, 12, 0, 0)
        out = m.get_moon(naive)
        self.assertIn("illuminated", out)

    def test_full_moon_known_date(self):
        # 2026-08-28 04:18 UTC is the August full moon (Sturgeon Moon).
        m = Moon()
        out = m.get_moon(_utc(2026, 8, 28, 4, 18))
        self.assertIn("Full Moon", out)
        self.assertIn("100% illuminated", out)

    def test_three_lines(self):
        m = Moon()
        out = m.get_moon(_utc(2026, 8, 26, 17, 0))
        self.assertEqual(len(out.split("\n")), 3)


if __name__ == "__main__":
    unittest.main()
