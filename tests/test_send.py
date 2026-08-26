"""Regression tests for reply-channel routing in _send.

Bug: the bot always replied to `^all` (channel broadcast) whenever
`DM_MODE: False`, even when the triggering message was a direct message
to the bot's own node. Replies must go back on the same channel the
message arrived on.
"""

import unittest
from unittest.mock import MagicMock

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


class TestSendReplyChannel(unittest.TestCase):

    def _dest(self, bot):
        return bot.interface.sendText.call_args[1]["destinationId"]

    def test_direct_message_replies_to_sender(self):
        bot = _make_bot()
        bot._reply_dest = 3770480103
        bot._send("hello", 3770480103, wantAck=True)
        self.assertEqual(self._dest(bot), 3770480103)

    def test_broadcast_replies_to_all(self):
        bot = _make_bot()
        bot._reply_dest = "^all"
        bot._send("hello", 3770480103, wantAck=True)
        self.assertEqual(self._dest(bot), "^all")

    def test_no_reply_dest_falls_back_to_dm_mode_false(self):
        # Scheduler-driven sends (no incoming packet) keep the old behaviour.
        bot = _make_bot()
        bot._reply_dest = None
        bot.dm_mode = False
        bot._send("hello", 3770480103, wantAck=False)
        self.assertEqual(self._dest(bot), "^all")

    def test_no_reply_dest_falls_back_to_dm_mode_true(self):
        bot = _make_bot()
        bot._reply_dest = None
        bot.dm_mode = True
        bot._send("hello", 3770480103, wantAck=False)
        self.assertEqual(self._dest(bot), 3770480103)


if __name__ == "__main__":
    unittest.main()
