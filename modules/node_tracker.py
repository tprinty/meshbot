import os
import sqlite3
import time


class NodeTracker:
    """Persistent per-node last-seen tracking for welcome messages.

    Records when a node is observed and reports whether it should be
    welcomed: never seen before, or not seen for `cooldown_days`.
    """

    def __init__(self, db_path, cooldown_days=30):
        self.db_path = db_path
        self.cooldown_days = cooldown_days
        directory = os.path.dirname(db_path)
        if directory:
            os.makedirs(directory, exist_ok=True)
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS seen_nodes ("
                "node_id TEXT PRIMARY KEY, "
                "last_seen INTEGER NOT NULL)"
            )

    def should_welcome(self, node_id):
        """Record a sighting and return True if the node should be welcomed.

        True when the node has never been seen, or its previous sighting was
        `cooldown_days` or more ago. Always updates the last-seen timestamp.
        """
        now = int(time.time())
        key = str(node_id)
        cooldown = self.cooldown_days * 86400
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT last_seen FROM seen_nodes WHERE node_id = ?",
                (key,),
            ).fetchone()
            welcome = row is None or (now - row[0]) >= cooldown
            conn.execute(
                "INSERT INTO seen_nodes (node_id, last_seen) VALUES (?, ?) "
                "ON CONFLICT(node_id) DO UPDATE SET last_seen = excluded.last_seen",
                (key, now),
            )
        return welcome
