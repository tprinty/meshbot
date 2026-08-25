"""Regression tests for the whois command dispatch.

The historical bugs:
1. `message_listener` passed the raw packet dict to `command_whois`, which
   expects the decoded text string — raised `AttributeError` for anyone who
   sent `#whois # <id>`.
2. `command_whois` had broken control flow that produced duplicate replies:
   a hex lookup that found nothing sent "No matching record" twice, and a hex
   lookup that succeeded still fell through to a short-name search and sent a
   spurious "No matching record" after the correct data.

These tests pin the corrected behavior.
"""

import sqlite3
import unittest
from unittest.mock import MagicMock, patch

import meshbot


def _make_bot():
    """Build a MeshBot with a mocked interface and no radio/network access."""
    bot = meshbot.MeshBot(serial_port=["/dev/null"], db="mpowered")
    bot.interface = MagicMock()
    bot.weather_info = "test weather"
    bot.tides_info = "test tides"
    bot.transmission_count = 0
    bot.dm_mode = False
    bot.firewall = False
    bot.dutycycle = False
    return bot


def _whois_packet(text):
    """Build a TEXT_MESSAGE_APP packet as delivered by the library."""
    return {
        "from": 3770480103,
        "to": 4294967295,
        "decoded": {"portnum": "TEXT_MESSAGE_APP", "text": text},
    }


def _sent_text(bot):
    """Return the text of the (single) message sent by the bot, or None."""
    if not bot.interface.sendText.called:
        return None
    return bot.interface.sendText.call_args[0][0]


class TestWhoisCommand(unittest.TestCase):

    def test_hex_lookup_match_sends_single_reply(self):
        """A hex node ID that resolves sends exactly one reply."""
        bot = _make_bot()
        with patch("meshbot.Whois") as MockWhois:
            MockWhois.return_value.search_nodes.return_value = (
                3661660496, "WeMoBot", "WeMo"
            )
            bot.command_whois("#whois # da408150", bot.interface, 3770480103)
        self.assertEqual(bot.interface.sendText.call_count, 1)
        text = _sent_text(bot)
        self.assertIn("3661660496", text)
        self.assertIn("WeMoBot", text)

    def test_hex_lookup_no_match_sends_single_reply(self):
        """A hex ID with no record sends exactly one 'no match' reply."""
        bot = _make_bot()
        with patch("meshbot.Whois") as MockWhois:
            MockWhois.return_value.search_nodes.return_value = None
            MockWhois.return_value.search_nodes_sn.return_value = None
            bot.command_whois("#whois # deadbeef", bot.interface, 3770480103)
        self.assertEqual(bot.interface.sendText.call_count, 1)
        self.assertIn("No matching record", _sent_text(bot))

    def test_short_name_lookup_match(self):
        """A non-hex query falls back to short-name search and replies once."""
        bot = _make_bot()
        with patch("meshbot.Whois") as MockWhois:
            MockWhois.return_value.search_nodes_sn.return_value = (
                3770480103, "TomPrinty tomp", "Tomp"
            )
            bot.command_whois("#whois # Tomp", bot.interface, 3770480103)
        self.assertEqual(bot.interface.sendText.call_count, 1)
        self.assertIn("Tomp", _sent_text(bot))

    def test_short_name_no_match(self):
        """A non-hex query with no record replies 'no match' once."""
        bot = _make_bot()
        with patch("meshbot.Whois") as MockWhois:
            MockWhois.return_value.search_nodes_sn.return_value = None
            bot.command_whois("#whois # nobody", bot.interface, 3770480103)
        self.assertEqual(bot.interface.sendText.call_count, 1)
        self.assertIn("No matching record", _sent_text(bot))

    def test_hex_query_falls_back_to_short_name(self):
        """A hex query with no ID match falls back to short-name lookup."""
        bot = _make_bot()
        with patch("meshbot.Whois") as MockWhois:
            MockWhois.return_value.search_nodes.return_value = None
            MockWhois.return_value.search_nodes_sn.return_value = (
                3770480103, "TomPrinty tomp", "Tomp"
            )
            # "abc123" is valid hex, so it won't raise ValueError, but has no
            # ID match; the bot should fall back to the short-name search.
            bot.command_whois("#whois # abc123", bot.interface, 3770480103)
        self.assertEqual(bot.interface.sendText.call_count, 1)
        self.assertIn("Tomp", _sent_text(bot))

    def test_database_error_does_not_crash(self):
        """A sqlite3 error returns a graceful message instead of raising."""
        bot = _make_bot()
        with patch(
            "meshbot.Whois", side_effect=sqlite3.DatabaseError("corrupt")
        ):
            bot.command_whois("#whois # da408150", bot.interface, 3770480103)
        self.assertEqual(bot.interface.sendText.call_count, 1)
        self.assertIn("database error", _sent_text(bot))

    def test_listener_dispatches_whois_without_crashing(self):
        """Regression: #whois on the mesh must not raise AttributeError."""
        bot = _make_bot()
        with patch("meshbot.Whois") as MockWhois:
            MockWhois.return_value.search_nodes.return_value = None
            MockWhois.return_value.search_nodes_sn.return_value = None
            # Before the fix this raised AttributeError (dict has no .split).
            bot.message_listener(
                _whois_packet("#whois # da408150"), bot.interface
            )
        self.assertTrue(bot.interface.sendText.called)


if __name__ == "__main__":
    unittest.main()
