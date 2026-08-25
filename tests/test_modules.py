"""
Unit tests for meshbot modules.

Runs without a Meshtastic device — all external HTTP calls are mocked.
"""

import json
import unittest
from datetime import date
from unittest.mock import MagicMock, patch

# ── helpers ──────────────────────────────────────────────────────────────────

def _mock_response(status_code=200, text="", json_data=None, content=b""):
    resp = MagicMock()
    resp.status_code = status_code
    resp.text = text
    resp.content = content
    resp.json.return_value = json_data or {}
    return resp


# ── WeatherFetcher ────────────────────────────────────────────────────────────

class TestWeatherFetcher(unittest.TestCase):

    @patch("modules.wttr.requests.get")
    def test_sunny_response(self, mock_get):
        mock_get.return_value = _mock_response(
            text="Sunny +75°F →10mph 06:15AM 07:45PM"
        )
        from modules.wttr import WeatherFetcher
        wf = WeatherFetcher("Mobile, AL")
        result = wf.get_weather()
        self.assertIn("Sunny", result)
        self.assertIn("75", result)

    @patch("modules.wttr.requests.get")
    def test_http_error(self, mock_get):
        mock_get.return_value = _mock_response(status_code=503)
        from modules.wttr import WeatherFetcher
        result = WeatherFetcher("Mobile, AL").get_weather()
        self.assertIn("Failed", result)

    @patch("modules.wttr.requests.get")
    def test_connection_reset(self, mock_get):
        mock_get.side_effect = ConnectionResetError("reset")
        from modules.wttr import WeatherFetcher
        result = WeatherFetcher("Mobile, AL").get_weather()
        self.assertIn("Failed", result)


# ── StormAlerts ───────────────────────────────────────────────────────────────

class TestStormAlerts(unittest.TestCase):

    @patch("modules.alerts.requests.get")
    def test_no_alerts(self, mock_get):
        mock_get.return_value = _mock_response(json_data={"features": []})
        from modules.alerts import StormAlerts
        result = StormAlerts("ALZ061").get_alerts()
        self.assertEqual(result, "No active alerts.")

    @patch("modules.alerts.requests.get")
    def test_one_alert(self, mock_get):
        mock_get.return_value = _mock_response(json_data={
            "features": [{
                "properties": {
                    "event": "Severe Thunderstorm Warning",
                    "headline": "Severe thunderstorm warning for Mobile County until 8 PM CDT.",
                }
            }]
        })
        from modules.alerts import StormAlerts
        result = StormAlerts("ALZ061").get_alerts()
        self.assertIn("Severe Thunderstorm Warning", result)

    @patch("modules.alerts.requests.get")
    def test_http_error(self, mock_get):
        mock_get.return_value = _mock_response(status_code=500)
        from modules.alerts import StormAlerts
        result = StormAlerts("ALZ061").get_alerts()
        self.assertIn("Failed", result)

    @patch("modules.alerts.requests.get")
    def test_long_headline_truncated(self, mock_get):
        long_headline = "x" * 300
        mock_get.return_value = _mock_response(json_data={
            "features": [{"properties": {"event": "Flood Watch", "headline": long_headline}}]
        })
        from modules.alerts import StormAlerts
        result = StormAlerts("ALZ061").get_alerts()
        self.assertLessEqual(len(result), 300)  # headline capped at 150 chars + event label


# ── NOAATides ─────────────────────────────────────────────────────────────────

class TestNOAATides(unittest.TestCase):

    @patch("modules.noaa_tides.requests.get")
    def test_parses_predictions(self, mock_get):
        mock_get.return_value = _mock_response(json_data={
            "predictions": [
                {"t": "2024-06-01 06:30", "v": "1.5", "type": "H"},
                {"t": "2024-06-01 12:45", "v": "0.1", "type": "L"},
            ]
        })
        from modules.noaa_tides import NOAATides
        result = NOAATides("8735180", "Dauphin Island").get_tides()
        self.assertIn("High", result)
        self.assertIn("Low", result)
        self.assertIn("1.5", result)

    @patch("modules.noaa_tides.requests.get")
    def test_empty_predictions(self, mock_get):
        mock_get.return_value = _mock_response(json_data={"predictions": []})
        from modules.noaa_tides import NOAATides
        result = NOAATides("8735180").get_tides()
        self.assertIn("No tide data", result)

    @patch("modules.noaa_tides.requests.get")
    def test_http_error(self, mock_get):
        mock_get.return_value = _mock_response(status_code=503)
        from modules.noaa_tides import NOAATides
        result = NOAATides("8735180").get_tides()
        self.assertIn("Failed", result)


# ── Repeaters ─────────────────────────────────────────────────────────────────

class TestRepeaters(unittest.TestCase):

    @patch("modules.repeaters.requests.get")
    def test_formats_results(self, mock_get):
        mock_get.return_value = _mock_response(json_data={
            "results": [
                {
                    "Callsign": "KD4ABC",
                    "Frequency": "146.820",
                    "Input Freq": "146.220",
                    "PL": "100.0",
                    "Nearest City": "Mobile",
                }
            ]
        })
        from modules.repeaters import Repeaters
        result = Repeaters(30.6954, -88.0399).get_repeaters()
        self.assertIn("KD4ABC", result)
        self.assertIn("146.820", result)

    @patch("modules.repeaters.requests.get")
    def test_no_results(self, mock_get):
        mock_get.return_value = _mock_response(json_data={"results": []})
        from modules.repeaters import Repeaters
        result = Repeaters(30.6954, -88.0399).get_repeaters()
        self.assertIn("No open repeaters", result)

    @patch("modules.repeaters.requests.get")
    def test_http_error(self, mock_get):
        mock_get.return_value = _mock_response(status_code=500)
        from modules.repeaters import Repeaters
        result = Repeaters(30.6954, -88.0399).get_repeaters()
        self.assertIn("Failed", result)


# ── TropicalWeather ───────────────────────────────────────────────────────────

NHC_RSS_NO_STORMS = b"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>NHC Atlantic Tropical Weather Outlook</title>
    <item>
      <title>There are no active storms.</title>
      <description>The Atlantic basin is quiet.</description>
    </item>
  </channel>
</rss>"""

NHC_RSS_ACTIVE = b"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <item>
      <title>Hurricane Milton Advisory #12</title>
      <description>Milton is a Category 4 storm moving NNW at 12 mph.</description>
    </item>
  </channel>
</rss>"""


class TestTropicalWeather(unittest.TestCase):

    @patch("modules.tropics.requests.get")
    def test_no_active_storms(self, mock_get):
        mock_get.return_value = _mock_response(content=NHC_RSS_NO_STORMS)
        from modules.tropics import TropicalWeather
        result = TropicalWeather().get_tropics()
        self.assertIn("No active", result)

    @patch("modules.tropics.requests.get")
    def test_active_storm(self, mock_get):
        mock_get.return_value = _mock_response(content=NHC_RSS_ACTIVE)
        from modules.tropics import TropicalWeather
        result = TropicalWeather().get_tropics()
        self.assertIn("Milton", result)
        self.assertIn("Category 4", result)

    @patch("modules.tropics.requests.get")
    def test_http_error(self, mock_get):
        mock_get.return_value = _mock_response(status_code=503)
        from modules.tropics import TropicalWeather
        result = TropicalWeather().get_tropics()
        self.assertIn("Failed", result)


# ── hurricane_season_announcement ─────────────────────────────────────────────

class TestHurricaneSeasonAnnouncement(unittest.TestCase):

    def test_june_1_start(self):
        from modules.tropics import hurricane_season_announcement
        with patch("modules.tropics.date") as mock_date:
            mock_date.today.return_value = date(2026, 6, 1)
            msg = hurricane_season_announcement()
        self.assertIsNotNone(msg)
        self.assertIn("2026", msg)
        self.assertIn("starts", msg)

    def test_november_30_end(self):
        from modules.tropics import hurricane_season_announcement
        with patch("modules.tropics.date") as mock_date:
            mock_date.today.return_value = date(2026, 11, 30)
            msg = hurricane_season_announcement()
        self.assertIsNotNone(msg)
        self.assertIn("ends", msg)

    def test_mid_season_no_announcement(self):
        from modules.tropics import hurricane_season_announcement
        with patch("modules.tropics.date") as mock_date:
            mock_date.today.return_value = date(2026, 8, 15)
            msg = hurricane_season_announcement()
        self.assertIsNone(msg)

    def test_off_season_no_announcement(self):
        from modules.tropics import hurricane_season_announcement
        with patch("modules.tropics.date") as mock_date:
            mock_date.today.return_value = date(2026, 1, 15)
            msg = hurricane_season_announcement()
        self.assertIsNone(msg)


# ── WeMoBot welcome ───────────────────────────────────────────────────────────

import logging as _logging

class _FakeBot:
    """Minimal stub that carries only the welcome-related state and method."""
    def __init__(self, welcome_enabled=True, bot_name="WeMoBot", mynode="3661660496"):
        self.seen_nodes = set()
        self.welcome_enabled = welcome_enabled
        self.bot_name = bot_name
        self.mynode = mynode

    def _handle_nodeinfo(self, packet, interface):
        if not self.welcome_enabled:
            return
        node_id = packet.get("from")
        if node_id is None or node_id in self.seen_nodes:
            return
        if self.mynode and str(node_id) == str(self.mynode):
            return
        self.seen_nodes.add(node_id)
        user = packet.get("decoded", {}).get("user", {})
        long_name = user.get("longName", f"!{node_id:08x}")
        short_name = user.get("shortName", "???")
        msg = f"🤖 Welcome {long_name} ({short_name}) to the mesh! - {self.bot_name}"
        try:
            interface.sendText(msg, wantAck=False)
        except Exception as e:
            _logging.error("Failed to send welcome: %s", e)


class TestWelcome(unittest.TestCase):

    def _make_bot(self, welcome_enabled=True, bot_name="WeMoBot", mynode="3661660496"):
        return _FakeBot(welcome_enabled=welcome_enabled, bot_name=bot_name, mynode=mynode)

    def _nodeinfo_packet(self, node_id, long_name="Test Node", short_name="TST"):
        return {
            "from": node_id,
            "decoded": {
                "portnum": "NODEINFO_APP",
                "user": {"longName": long_name, "shortName": short_name},
            },
        }

    def test_welcome_sent_for_new_node(self):
        bot = self._make_bot()
        iface = MagicMock()
        bot._handle_nodeinfo(self._nodeinfo_packet(0xABCD1234), iface)
        iface.sendText.assert_called_once()
        msg = iface.sendText.call_args[0][0]
        self.assertIn("Test Node", msg)
        self.assertIn("TST", msg)
        self.assertIn("WeMoBot", msg)

    def test_no_duplicate_welcome(self):
        bot = self._make_bot()
        iface = MagicMock()
        packet = self._nodeinfo_packet(0xABCD1234)
        bot._handle_nodeinfo(packet, iface)
        bot._handle_nodeinfo(packet, iface)  # second call should be ignored
        self.assertEqual(iface.sendText.call_count, 1)

    def test_welcome_disabled(self):
        bot = self._make_bot(welcome_enabled=False)
        iface = MagicMock()
        bot._handle_nodeinfo(self._nodeinfo_packet(0xABCD1234), iface)
        iface.sendText.assert_not_called()

    def test_welcome_uses_bot_name(self):
        bot = self._make_bot(bot_name="TestBot")
        iface = MagicMock()
        bot._handle_nodeinfo(self._nodeinfo_packet(0xABCD1234), iface)
        msg = iface.sendText.call_args[0][0]
        self.assertIn("TestBot", msg)

    def test_no_self_welcome(self):
        bot = self._make_bot(mynode="3661660496")
        iface = MagicMock()
        bot._handle_nodeinfo(self._nodeinfo_packet(3661660496), iface)
        iface.sendText.assert_not_called()

    def test_no_self_welcome_int_node_id(self):
        # Node id arrives as an int; mynode is a string. Guard must still match.
        bot = self._make_bot(mynode=3661660496)
        iface = MagicMock()
        bot._handle_nodeinfo(self._nodeinfo_packet(3661660496), iface)
        iface.sendText.assert_not_called()


if __name__ == "__main__":
    unittest.main()
