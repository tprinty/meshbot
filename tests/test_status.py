"""Tests for the operator-only #status command.

Covers operator gating, always-direct reply, node table formatting,
and config inertness when OPERATOR_NODE is unset.
"""

import unittest
from unittest.mock import MagicMock

import meshbot


def _make_bot(operator_node="3770480103", status_nodes=("3661660496", "3770480103", "1578062984")):
    bot = meshbot.MeshBot(serial_port=["/dev/null"], db="mpowered")
    bot.interface = MagicMock()
    bot.operator_node = operator_node
    bot.status_nodes = [str(n) for n in status_nodes]
    bot.transmission_count = 0
    bot._reply_dest = None
    return bot


def _node(num, name="Test Node", last_heard=None, snr=None, battery=None):
    n = {"user": {"shortName": name, "longName": name + " long"}}
    if last_heard is not None:
        n["lastHeard"] = last_heard
    if snr is not None:
        n["snr"] = snr
    if battery is not None:
        n["deviceMetrics"] = {"batteryLevel": battery}
    return n


class TestStatusCommand(unittest.TestCase):

    def _send_text(self, bot):
        return bot.interface.sendText.call_args[0][0]

    def test_operator_gets_report(self):
        bot = _make_bot()
        import time
        now = int(time.time())
        bot.interface.nodesByNum = {
            3661660496: _node(3661660496, "WeMoBot", last_heard=now - 300, snr=7.0, battery=101),
            3770480103: _node(3770480103, "Tomp", last_heard=now - 120, snr=7.0),
            1578062984: _node(1578062984, "WMR1", last_heard=now - 28800, battery=89),
        }
        # Production passes an int sender (packet["from"]).
        bot.command_status(3770480103)
        text = self._send_text(bot)
        self.assertIn("WeMo:", text)
        self.assertIn("WeMoBot", text)
        self.assertIn("Tomp", text)
        self.assertIn("WMR1", text)
        self.assertIn("SNR 7.0", text)
        self.assertIn("101% batt", text)
        self.assertIn("89% batt", text)

    def test_non_operator_ignored_silently(self):
        bot = _make_bot()
        bot.interface.nodesByNum = {3661660496: _node(3661660496, "WeMoBot")}
        bot.command_status(4210449849)  # ScrimJim (int, as in production)
        bot.interface.sendText.assert_not_called()

    def test_reply_is_direct_even_on_broadcast(self):
        bot = _make_bot()
        import time
        now = int(time.time())
        bot.interface.nodesByNum = {3770480103: _node(3770480103, "Tomp", last_heard=now)}
        # Simulate the command arriving on a broadcast channel: _reply_dest was ^all.
        bot._reply_dest = "^all"
        bot.command_status(3770480103)
        dest = bot.interface.sendText.call_args[1]["destinationId"]
        self.assertEqual(dest, 3770480103)  # int, matching production

    def test_inert_without_operator_node(self):
        bot = _make_bot(operator_node=None)
        bot.command_status("3770480103")
        bot.interface.sendText.assert_not_called()

    def test_missing_node_reports_not_seen(self):
        bot = _make_bot()
        import time
        now = int(time.time())
        bot.interface.nodesByNum = {3661660496: _node(3661660496, "WeMoBot", last_heard=now)}
        bot.command_status("3770480103")
        text = self._send_text(bot)
        self.assertIn("not seen", text)

    def test_no_status_nodes_configured(self):
        bot = _make_bot(status_nodes=())
        bot.command_status("3770480103")
        text = self._send_text(bot)
        self.assertIn("No monitored nodes", text)


if __name__ == "__main__":
    unittest.main()
