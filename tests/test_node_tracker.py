"""Regression tests for the persistent welcome node tracker."""

import sqlite3
import tempfile
import time
import unittest

from modules.node_tracker import NodeTracker


class TestNodeTracker(unittest.TestCase):

    def _make(self, cooldown_days=30):
        tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        tmp.close()
        self.addCleanup(lambda: __import__("os").unlink(tmp.name))
        return NodeTracker(tmp.name, cooldown_days=cooldown_days), tmp.name

    def test_never_seen_welcomes(self):
        tracker, _ = self._make()
        self.assertTrue(tracker.should_welcome(3770480103))

    def test_recently_seen_does_not_welcome(self):
        tracker, _ = self._make()
        self.assertTrue(tracker.should_welcome(3770480103))
        # Same node seen again moments later — no welcome.
        self.assertFalse(tracker.should_welcome(3770480103))

    def test_returning_after_cooldown_welcomes(self):
        tracker, db = self._make(cooldown_days=30)
        self.assertTrue(tracker.should_welcome(3770480103))
        # Backdate the last-seen to 31 days ago.
        old = int(time.time()) - (31 * 86400)
        with sqlite3.connect(db) as conn:
            conn.execute(
                "UPDATE seen_nodes SET last_seen = ? WHERE node_id = ?",
                (old, "3770480103"),
            )
        self.assertTrue(tracker.should_welcome(3770480103))

    def test_within_cooldown_does_not_welcome(self):
        tracker, db = self._make(cooldown_days=30)
        self.assertTrue(tracker.should_welcome(3770480103))
        # Backdate to 10 days ago — still within the cooldown.
        ten_days = int(time.time()) - (10 * 86400)
        with sqlite3.connect(db) as conn:
            conn.execute(
                "UPDATE seen_nodes SET last_seen = ? WHERE node_id = ?",
                (ten_days, "3770480103"),
            )
        self.assertFalse(tracker.should_welcome(3770480103))

    def test_int_and_string_node_ids_share_a_record(self):
        tracker, _ = self._make()
        self.assertTrue(tracker.should_welcome(3770480103))
        # Same node, this time as a string — must not welcome again.
        self.assertFalse(tracker.should_welcome("3770480103"))

    def test_welcome_records_timestamp(self):
        tracker, db = self._make()
        before = int(time.time())
        tracker.should_welcome(3770480103)
        with sqlite3.connect(db) as conn:
            last_seen = conn.execute(
                "SELECT last_seen FROM seen_nodes WHERE node_id = ?",
                ("3770480103",),
            ).fetchone()[0]
        self.assertGreaterEqual(last_seen, before)


if __name__ == "__main__":
    unittest.main()
