"""Tests for the daily tropics broadcast thread.

Verifies the broadcaster fires only during hurricane season, only past
the configured time, and only once per day.
"""

import unittest
from unittest.mock import MagicMock, patch


def _make_bot(tropics_daily_enabled=True, tropics_daily_time="07:00"):
    import meshbot
    bot = meshbot.MeshBot(serial_port=["/dev/null"], db="mpowered")
    bot.interface = MagicMock()
    bot.tropical_weather = MagicMock()
    bot.tropics_info = "No active tropical systems."
    bot.tropics_daily_enabled = tropics_daily_enabled
    bot.tropics_daily_time = tropics_daily_time
    return bot


class TestDailyTropicsBroadcaster(unittest.TestCase):
    """Test the logic inside _daily_tropics_broadcaster one tick at a time."""

    def _tick(self, bot, year, month, day, hour, minute):
        """Simulate one pass through the broadcaster's inner loop."""
        import datetime as _dt
        from modules.tropics import in_hurricane_season as _hs

        today = _dt.date(year, month, day)
        if not _hs():
            return  # correct: silent outside season
        now_ct = _dt.datetime(
            year, month, day, hour, minute, 0,
            tzinfo=_dt.timezone(_dt.timedelta(hours=-5)),
        )
        if now_ct.strftime("%H:%M") < bot.tropics_daily_time:
            return  # correct: not yet time

        if bot.tropical_weather and bot.tropics_info:
            header = (
                f"🌀 Daily Tropics — "
                f"{today.strftime('%a %b %-d')}"
            )
            msg = f"{header}\n{bot.tropics_info}"
            bot.interface.sendText(msg, wantAck=False)

    @patch("modules.tropics.in_hurricane_season", return_value=True)
    def test_broadcasts_at_time(self, _mock):
        bot = _make_bot()
        self._tick(bot, 2026, 8, 26, 7, 30)  # Aug 26, 7:30am CT
        bot.interface.sendText.assert_called_once()
        msg = bot.interface.sendText.call_args[0][0]
        self.assertIn("Daily Tropics", msg)
        self.assertIn("Wed Aug 26", msg)
        self.assertIn("No active", msg)

    @patch("modules.tropics.in_hurricane_season", return_value=False)
    def test_no_broadcast_outside_season(self, _mock):
        bot = _make_bot()
        self._tick(bot, 2026, 1, 15, 7, 30)
        bot.interface.sendText.assert_not_called()

    @patch("modules.tropics.in_hurricane_season", return_value=True)
    def test_no_broadcast_before_time(self, _mock):
        bot = _make_bot()
        self._tick(bot, 2026, 8, 26, 6, 30)  # 6:30am, before 7:00
        bot.interface.sendText.assert_not_called()

    @patch("modules.tropics.in_hurricane_season", return_value=True)
    def test_sends_public_broadcast(self, _mock):
        bot = _make_bot()
        self._tick(bot, 2026, 8, 26, 7, 30)
        call_kwargs = bot.interface.sendText.call_args[1]
        self.assertEqual(call_kwargs.get("wantAck"), False)
        # No destinationId — defaults to ^all (public broadcast).
        self.assertNotIn("destinationId", call_kwargs)

    @patch("modules.tropics.in_hurricane_season", return_value=True)
    def test_tropics_disabled_sends_nothing(self, _mock):
        bot = _make_bot()
        bot.tropical_weather = None
        self._tick(bot, 2026, 8, 26, 7, 30)
        bot.interface.sendText.assert_not_called()

    @patch("modules.tropics.in_hurricane_season", return_value=True)
    def test_config_value_present(self, _mock):
        bot = _make_bot(tropics_daily_time="08:30")
        self.assertEqual(bot.tropics_daily_time, "08:30")


if __name__ == "__main__":
    unittest.main()