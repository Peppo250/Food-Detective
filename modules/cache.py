"""
modules/cache.py — SQLite-backed ingredient cache with 90-day TTL.

Schema:
    ingredients(
        key         TEXT PRIMARY KEY,   -- normalised ingredient name
        data        TEXT,               -- JSON blob
        cached_at   INTEGER,            -- unix timestamp of insert
        expires_at  INTEGER             -- unix timestamp of expiry (cached_at + 90 days)
    )

Cleanup strategy:
  - purge_expired() is called on every app startup
  - A background thread calls it once per day while the app runs
"""
import json
import sqlite3
import time
import threading
import os
import re

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "ingredients.db")
TTL_SECONDS = 90 * 24 * 60 * 60  # 90 days
CLEANUP_INTERVAL = 24 * 60 * 60   # 1 day


class IngredientCache:
    def __init__(self, db_path: str = DB_PATH):
        self._db_path = os.path.abspath(db_path)
        os.makedirs(os.path.dirname(self._db_path), exist_ok=True)
        self._init_db()
        self._start_cleanup_scheduler()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get(self, name: str) -> dict | None:
        """Return cached data for ingredient or None if missing/expired."""
        key = _normalise_key(name)
        now = int(time.time())
        with self._connect() as con:
            row = con.execute(
                "SELECT data FROM ingredients WHERE key = ? AND expires_at > ?",
                (key, now),
            ).fetchone()
        if row:
            return json.loads(row[0])
        return None

    def set(self, name: str, data: dict) -> None:
        """Insert or replace a cache entry."""
        key = _normalise_key(name)
        now = int(time.time())
        expires = now + TTL_SECONDS
        with self._connect() as con:
            con.execute(
                """
                INSERT OR REPLACE INTO ingredients (key, data, cached_at, expires_at)
                VALUES (?, ?, ?, ?)
                """,
                (key, json.dumps(data), now, expires),
            )

    def purge_expired(self) -> int:
        """Delete all expired entries. Returns number of rows deleted."""
        now = int(time.time())
        with self._connect() as con:
            cur = con.execute(
                "DELETE FROM ingredients WHERE expires_at <= ?", (now,)
            )
            deleted = cur.rowcount
        return deleted

    def stats(self) -> dict:
        now = int(time.time())
        with self._connect() as con:
            total = con.execute("SELECT COUNT(*) FROM ingredients").fetchone()[0]
            active = con.execute(
                "SELECT COUNT(*) FROM ingredients WHERE expires_at > ?", (now,)
            ).fetchone()[0]
        return {"total": total, "active": active, "expired_purged": total - active}

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _init_db(self):
        with self._connect() as con:
            con.execute("""
                CREATE TABLE IF NOT EXISTS ingredients (
                    key        TEXT PRIMARY KEY,
                    data       TEXT NOT NULL,
                    cached_at  INTEGER NOT NULL,
                    expires_at INTEGER NOT NULL
                )
            """)
            con.execute(
                "CREATE INDEX IF NOT EXISTS idx_expires ON ingredients(expires_at)"
            )

    def _connect(self) -> sqlite3.Connection:
        con = sqlite3.connect(self._db_path, check_same_thread=False)
        con.row_factory = sqlite3.Row
        return con

    def _start_cleanup_scheduler(self):
        def _loop():
            while True:
                time.sleep(CLEANUP_INTERVAL)
                try:
                    n = self.purge_expired()
                    if n:
                        print(f"[cache] purged {n} expired entries")
                except Exception as e:
                    print(f"[cache] cleanup error: {e}")

        t = threading.Thread(target=_loop, daemon=True)
        t.start()


def _normalise_key(name: str) -> str:
    """Lowercase, strip extra whitespace, remove plurals for better hit rate."""
    key = name.lower().strip()
    key = re.sub(r"\s+", " ", key)
    # Strip trailing 's' for simple plural normalisation (salt → salt, sugars → sugar)
    key = re.sub(r"s\b", "", key)
    return key
