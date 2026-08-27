"""Regression test: timezone mismatch between the dedup guard and the
schedule clock in the daily broadcasters.

Root cause: the ``sent_today`` guard used ``datetime.date.today()`` (host
UTC) but the time-of-day check used Central (-5).  On a restart between
00:00-05:00 UTC the UTC date has already rolled over while it is still
the previous evening in Central — the guard marks Central's *tomorrow* as
already-handled and silently skips the next morning's broadcast.

Fix: ``meshtastic._central_now()`` returns a single Central-time value
from which both the dedup date and the schedule time are derived, so
they always agree.
"""

import unittest
from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

class _StopLoop(Exception):
    pass


def _drive(broadcaster, times):
    """Run ``broadcaster`` for ``len(times)`` loop ticks.

    ``times`` is a list of ``(year, month, day, hour, minute)`` tuples
    interpreted as wall-clock Central time.  The real ``_central_now()``
    is mocked to return these in order; ``time.sleep`` is mocked to let
    the loop proceed but raises ``_StopLoop`` after the last tick so the
    infinite loop doesn't need thread-killing.
    """
    import datetime as _dt
    import meshbot

    nows = iter([
        _dt.datetime(y, mo, d, h, mi, 0,
                     tzinfo=_dt.timezone(_dt.timedelta(hours=-5)))
        for (y, mo, d, h, mi) in times
    ])

    sleeps = 0

    def fake_now():
        return next(nows)

    def fake_sleep(secs):
        nonlocal sleeps
        sleeps += 1
        if sleeps >= len(times):
            raise _StopLoop()

    with patch.object(meshbot, "_central_now", side_effect=fake_now), \
         patch.object(meshbot.time, "sleep", side_effect=fake_sleep):
        try:
            broadcaster()
        except _StopLoop:
            pass


def _make_forecast_bot(**kw):
    import meshbot
    bot = meshbot.MeshBot(serial_port=["/dev/null"], db="mpowered")
    bot.interface = MagicMock()
    bot.weather_info = "☀️ Sunny\n🌡️ +98°F\n💨 ↑3mph\n"
    bot.forecast_daily_enabled = kw.get("forecast_daily_enabled", True)
    bot.forecast_daily_time = kw.get("forecast_daily_time", "07:00")
    return bot


def _make_tropics_bot(**kw):
    import meshbot
    bot = meshbot.MeshBot(serial_port=["/dev/null"], db="mpowered")
    bot.interface = MagicMock()
    bot.tropical_weather = True          # truthy = enabled
    bot.tropics_info = "No active tropical cyclones in the Atlantic."
    bot.tropics_daily_enabled = kw.get("tropics_daily_enabled", True)
    bot.tropics_daily_time = kw.get("tropics_daily_time", "07:00")
    return bot


# ---------------------------------------------------------------------------
# forecast broadcaster
# ---------------------------------------------------------------------------

class TestDailyForecastTimezoneRegression(unittest.TestCase):

    def test_restart_in_mismatch_window_broadcasts_next_morning(self):
        """Restart at 20:11 CT (01:11 UTC — mismatch) must not block the
        7am CT broadcast the next day."""
        bot = _make_forecast_bot()

        _drive(bot._daily_forecast_broadcaster, [
            (2026, 8, 26, 20, 11),   # evening — UTC date is Aug 27
            (2026, 8, 27,  7,  5),   # next morning within 15-min window
        ])

        bot.interface.sendText.assert_called_once()
        msg = bot.interface.sendText.call_args[0][0]
        self.assertIn("West Mobile", msg)
        self.assertIn("Thu Aug 27", msg)

    def test_restart_late_in_day_still_broadcasts_tomorrow(self):
        """Restart at 10:15 CT (after the 15-min window closes) must still
        fire tomorrow, not tomorrow-tomorrow."""
        bot = _make_forecast_bot()

        _drive(bot._daily_forecast_broadcaster, [
            (2026, 8, 26, 10, 15),   # too late for today's slot
            (2026, 8, 27,  7,  0),   # tomorrow — should fire
        ])

        bot.interface.sendText.assert_called_once()
        msg = bot.interface.sendText.call_args[0][0]
        self.assertIn("Thu Aug 27", msg)

    # Sanity checks — these are the same scenarios the existing tests
    # cover, but run through the REAL broadcaster so they're honest.

    def test_broadcasts_at_configured_time(self):
        bot = _make_forecast_bot()
        _drive(bot._daily_forecast_broadcaster, [
            (2026, 8, 27, 7, 5),
        ])
        bot.interface.sendText.assert_called_once()

    def test_no_broadcast_too_early(self):
        bot = _make_forecast_bot()
        # 6:30 am — the broadcaster will poll every 15 min; give it two
        # pre-time ticks (6:30, 6:45) to prove it stays silent.
        _drive(bot._daily_forecast_broadcaster, [
            (2026, 8, 27, 6, 30),
            (2026, 8, 27, 6, 45),
        ])
        bot.interface.sendText.assert_not_called()

    def test_no_broadcast_too_late(self):
        bot = _make_forecast_bot()
        _drive(bot._daily_forecast_broadcaster, [
            (2026, 8, 27, 7, 30),
        ])
        bot.interface.sendText.assert_not_called()


# ---------------------------------------------------------------------------
# tropics broadcaster
# ---------------------------------------------------------------------------

class TestDailyTropicsTimezoneRegression(unittest.TestCase):

    def test_restart_in_mismatch_window_broadcasts_next_morning(self):
        """Same UTC/Central mismatch bug for the tropics broadcaster."""
        bot = _make_tropics_bot()

        with patch("modules.tropics.in_hurricane_season", return_value=True):
            _drive(bot._daily_tropics_broadcaster, [
                (2026, 8, 26, 20, 11),
                (2026, 8, 27,  7,  5),
            ])

        bot.interface.sendText.assert_called_once()
        msg = bot.interface.sendText.call_args[0][0]
        self.assertIn("Daily Tropics", msg)
        self.assertIn("Thu Aug 27", msg)

    def test_silent_outside_hurricane_season(self):
        """Outside hurricane season the broadcaster must not fire even
        when the time-of-day window matches."""
        bot = _make_tropics_bot()

        with patch("modules.tropics.in_hurricane_season", return_value=False):
            _drive(bot._daily_tropics_broadcaster, [
                (2026, 12, 15, 7, 5),  # Dec — NOT hurricane season
            ])

        bot.interface.sendText.assert_not_called()

    def test_broadcasts_at_configured_time(self):
        bot = _make_tropics_bot()

        with patch("modules.tropics.in_hurricane_season", return_value=True):
            _drive(bot._daily_tropics_broadcaster, [
                (2026, 8, 27, 7, 5),
            ])

        bot.interface.sendText.assert_called_once()
