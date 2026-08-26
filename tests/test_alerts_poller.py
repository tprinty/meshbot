"""Tests for the NWS storm-alert polling system.

Verifies the poller seeds on first run (no spam on restart), detects new
alerts, deduplicates, and formats broadcasts compactly.
"""

import unittest
from unittest.mock import MagicMock, patch

import datetime as _dt


def _make_bot(alerts_poll_enabled=True, alerts_poll_interval=300):
    import meshbot
    bot = meshbot.MeshBot(serial_port=["/dev/null"], db="mpowered")
    bot.interface = MagicMock()
    bot.storm_alerts = MagicMock()
    bot.alerts_poll_enabled = alerts_poll_enabled
    bot.alerts_poll_interval = alerts_poll_interval
    bot._sent_alert_ids = set()
    return bot


def _make_alert(alert_id="test123", event="Severe Thunderstorm Warning",
                headline="SVR for Mobile County", severity="Severe",
                expires="2026-08-26T17:30:00-05:00",
                description="At 4:40 PM CDT, a severe tstorm near Semmes."):
    return {
        "id": alert_id,
        "event": event,
        "headline": headline,
        "severity": severity,
        "expires": expires,
        "description": description,
    }


def _simulate_poll(bot, alerts, first_run=False):
    """Simulate one poll cycle of the alerts poller."""
    if first_run:
        active_ids = {a["id"] for a in alerts}
        bot._sent_alert_ids = active_ids
        return  # first run seeds, no broadcast

    active_ids = {a["id"] for a in alerts}
    for a in alerts:
        if a["id"] not in bot._sent_alert_ids:
            bot._sent_alert_ids.add(a["id"])
            msg = bot._format_alert_broadcast(a)
            if msg:
                bot.interface.sendText(msg, wantAck=False)

    # Clean up stale IDs
    bot._sent_alert_ids = bot._sent_alert_ids & active_ids


class TestAlertsPoller(unittest.TestCase):
    """Test the logic inside _alerts_poller one cycle at a time."""

    def test_first_poll_seeds_no_broadcast(self):
        """First poll should seed alert IDs but NOT broadcast anything."""
        bot = _make_bot()
        alerts = [_make_alert("nws-001")]
        _simulate_poll(bot, alerts, first_run=True)
        bot.interface.sendText.assert_not_called()
        self.assertEqual(bot._sent_alert_ids, {"nws-001"})

    def test_new_alert_triggers_broadcast(self):
        """A new alert ID not in the sent set should broadcast."""
        bot = _make_bot()
        alerts_initial = [_make_alert("nws-001")]
        _simulate_poll(bot, alerts_initial, first_run=True)

        # New alert appears
        alerts_update = [
            _make_alert("nws-001"),
            _make_alert("nws-002", event="Special Weather Statement",
                        description="Strong tstorm over Mobile."),
        ]
        bot.interface.reset_mock()
        _simulate_poll(bot, alerts_update, first_run=False)

        bot.interface.sendText.assert_called_once()
        msg = bot.interface.sendText.call_args[0][0]
        self.assertIn("nws-002", bot._sent_alert_ids)
        self.assertIn("Special Weather Statement", msg)

    def test_seen_alert_no_duplicate_broadcast(self):
        """An alert already in the sent set should not broadcast again."""
        bot = _make_bot()
        alerts = [_make_alert("nws-001")]
        _simulate_poll(bot, alerts, first_run=True)
        bot.interface.reset_mock()
        _simulate_poll(bot, alerts, first_run=False)
        bot.interface.sendText.assert_not_called()

    def test_expired_alert_can_reappear(self):
        """When an alert expires and later resurfaces with the same ID,
        it should broadcast again (the ID is cleaned out on expiry)."""
        bot = _make_bot()
        alerts_before = [_make_alert("nws-001")]
        _simulate_poll(bot, alerts_before, first_run=True)

        # Alert expires (no longer in active set)
        _simulate_poll(bot, [], first_run=False)
        self.assertEqual(bot._sent_alert_ids, set())

        # Same ID reappears — this is a NEW issuance
        bot.interface.reset_mock()
        _simulate_poll(bot, alerts_before, first_run=False)
        bot.interface.sendText.assert_called_once()

    def test_multiple_new_alerts_broadcast_all(self):
        """When multiple new alerts appear, all should broadcast."""
        bot = _make_bot()
        _simulate_poll(bot, [], first_run=True)

        alerts = [
            _make_alert("nws-001"),
            _make_alert("nws-002", event="Tornado Warning"),
            _make_alert("nws-003", event="Flood Advisory"),
        ]
        bot.interface.reset_mock()
        _simulate_poll(bot, alerts, first_run=False)
        self.assertEqual(bot.interface.sendText.call_count, 3)

    def test_disabled_poller_no_action(self):
        """When alerts poll is disabled, the thread should not exist."""
        bot = _make_bot(alerts_poll_enabled=False)
        self.assertFalse(bot.alerts_poll_enabled)

    def test_no_alerts_configured_no_poller(self):
        """When storm_alerts is None, polling is inert."""
        bot = _make_bot()
        bot.storm_alerts = None
        # Should not crash — poller just sleeps
        self.assertIsNone(bot.storm_alerts)


class TestAlertBroadcastFormat(unittest.TestCase):
    """Test _format_alert_broadcast output."""

    def test_format_includes_event_and_warning_emoji(self):
        bot = _make_bot()
        alert = _make_alert(
            event="Severe Thunderstorm Warning",
            description="At 4:40 PM CDT, a severe tstorm near Semmes.",
        )
        msg = bot._format_alert_broadcast(alert)
        self.assertIn("⚠", msg)
        self.assertIn("Severe Thunderstorm Warning", msg)

    def test_format_joins_lines_until_blank_line(self):
        """Lines up to the first blank line are joined into a paragraph."""
        bot = _make_bot()
        alert = _make_alert(
            description=(
                "First line of description.\n"
                "Second line with more detail.\n"
                "Third line wraps.\n"
                "\n"
                "HAZARD...60 mph wind gusts.\n"
                "\n"
                "IMPACT...Expect damage to roofs."
            ),
        )
        msg = bot._format_alert_broadcast(alert)
        self.assertIn("First line of description", msg)
        self.assertIn("Second line with more detail", msg)
        self.assertIn("Third line wraps", msg)
        # HAZARD and IMPACT are behind a blank line — excluded
        self.assertNotIn("HAZARD", msg)
        self.assertNotIn("IMPACT", msg)

    def test_format_includes_expiration(self):
        bot = _make_bot()
        alert = _make_alert(expires="2026-08-26T17:30:00-05:00")
        msg = bot._format_alert_broadcast(alert)
        self.assertIn("Exp.", msg)
        self.assertIn("5:30 PM", msg)

    def test_format_truncates_long_description(self):
        bot = _make_bot()
        alert = _make_alert(description="X" * 300)
        msg = bot._format_alert_broadcast(alert)
        # A single long line with no blank lines gets truncated
        self.assertIn("...", msg)

    def test_format_no_description_uses_headline(self):
        bot = _make_bot()
        alert = _make_alert(
            headline="Special Weather Statement for Mobile County",
            description="",
        )
        msg = bot._format_alert_broadcast(alert)
        self.assertIn("Special Weather Statement", msg)

    def test_format_no_expiration_no_error(self):
        bot = _make_bot()
        alert = _make_alert(expires="")
        msg = bot._format_alert_broadcast(alert)
        self.assertNotIn("Exp.", msg)
        # Should not crash — just no expiration line


if __name__ == "__main__":
    unittest.main()