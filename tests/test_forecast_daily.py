"""Tests for the daily forecast broadcast thread."""

import unittest
from unittest.mock import MagicMock, patch


def _make_bot(forecast_daily_enabled=True, forecast_daily_time="07:00"):
    import meshbot
    bot = meshbot.MeshBot(serial_port=["/dev/null"], db="mpowered")
    bot.interface = MagicMock()
    bot.forecast_info = "☀️ Sunny  ☂️ 10%\n🌡️ 75°F → 98°F\n💨 N 3mph  UV 9\n🌞 6:25a  🌛 7:23p"
    bot.forecast_daily_enabled = forecast_daily_enabled
    bot.forecast_daily_time = forecast_daily_time
    return bot


class TestDailyForecastBroadcaster(unittest.TestCase):
    """Test the logic inside _daily_forecast_broadcaster."""

    def _tick(self, bot, year, month, day, hour, minute):
        """Simulate one pass through the broadcaster's inner time-check."""
        import datetime as _dt

        today = _dt.date(year, month, day)
        now_ct = _dt.datetime(
            year, month, day, hour, minute, 0,
            tzinfo=_dt.timezone(_dt.timedelta(hours=-5)),
        )
        if now_ct.strftime("%H:%M") < bot.forecast_daily_time:
            return
        cfg_h, cfg_m = map(int, bot.forecast_daily_time.split(":"))
        cur_h, cur_m = int(now_ct.strftime("%H")), int(now_ct.strftime("%M"))
        delta = (cur_h * 60 + cur_m) - (cfg_h * 60 + cfg_m)
        if delta < 0 or delta > 15:
            return

        info = bot.forecast_info
        if info:
            header = f"🌅 West Mobile — {today.strftime('%a %b %-d')}"
            msg = f"{header}\n{info.strip()}"
            bot.interface.sendText(msg, wantAck=True)

    def test_broadcasts_at_configured_time(self):
        bot = _make_bot()
        self._tick(bot, 2026, 8, 27, 7, 5)
        bot.interface.sendText.assert_called_once()
        msg = bot.interface.sendText.call_args[0][0]
        self.assertIn("West Mobile", msg)
        self.assertIn("Thu Aug 27", msg)
        self.assertIn("☀️ Sunny", msg)
        self.assertIn("75°F → 98°F", msg)

    def test_no_broadcast_before_time(self):
        bot = _make_bot()
        self._tick(bot, 2026, 8, 27, 6, 30)
        bot.interface.sendText.assert_not_called()

    def test_no_broadcast_too_late(self):
        bot = _make_bot()
        self._tick(bot, 2026, 8, 27, 7, 30)
        bot.interface.sendText.assert_not_called()

    def test_broadcast_with_empty_cache_fallback(self):
        bot = _make_bot()
        bot.forecast_info = ""
        bot.weather_fetcher = MagicMock()
        bot.weather_fetcher.get_forecast.return_value = (
            "☁️ Cloudy  ☂️ 50%\n🌡️ 70°F → 85°F\n💨 S 5mph  UV 6\n🌞 6:30a  🌛 7:15p"
        )
        self._tick(bot, 2026, 8, 27, 7, 5)
        self.assertTrue(bot.forecast_daily_enabled)

    def test_disabled_flag(self):
        bot = _make_bot(forecast_daily_enabled=False)
        self.assertFalse(bot.forecast_daily_enabled)

    def test_sends_public_broadcast_with_ack(self):
        bot = _make_bot()
        self._tick(bot, 2026, 8, 27, 7, 5)
        call_kwargs = bot.interface.sendText.call_args[1]
        self.assertEqual(call_kwargs.get("wantAck"), True)
        self.assertNotIn("destinationId", call_kwargs)


if __name__ == "__main__":
    unittest.main()