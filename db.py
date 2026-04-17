# db.py
import sqlite3
from datetime import datetime, timedelta


class Database:
    def __init__(self, path: str = "tradeagent.db"):
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row
        self._create_tables()

    def _create_tables(self):
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS watchlist (
                symbol TEXT PRIMARY KEY,
                source TEXT NOT NULL,
                added_at TEXT NOT NULL,
                expires_at TEXT
            );
            CREATE TABLE IF NOT EXISTS portfolio (
                symbol TEXT PRIMARY KEY,
                added_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS cooldowns (
                symbol TEXT NOT NULL,
                alert_type TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                PRIMARY KEY (symbol, alert_type)
            );
        """)
        self.conn.commit()

    def add_watchlist(self, symbol: str, source: str = "manual"):
        self.conn.execute(
            "INSERT OR IGNORE INTO watchlist (symbol, source, added_at) VALUES (?, ?, ?)",
            (symbol, source, datetime.now().isoformat()),
        )
        self.conn.commit()

    def remove_watchlist(self, symbol: str):
        self.conn.execute("DELETE FROM watchlist WHERE symbol = ?", (symbol,))
        self.conn.commit()

    def expire_watchlist(self, symbol: str, days: int = 7):
        expires = (datetime.now() + timedelta(days=days)).isoformat()
        self.conn.execute(
            "UPDATE watchlist SET expires_at = ? WHERE symbol = ?", (expires, symbol)
        )
        self.conn.commit()

    def get_watchlist(self) -> list[dict]:
        now = datetime.now().isoformat()
        rows = self.conn.execute(
            "SELECT * FROM watchlist WHERE expires_at IS NULL OR expires_at > ?",
            (now,),
        ).fetchall()
        return [dict(r) for r in rows]

    def add_position(self, symbol: str):
        self.conn.execute(
            "INSERT OR IGNORE INTO portfolio (symbol, added_at) VALUES (?, ?)",
            (symbol, datetime.now().isoformat()),
        )
        self.conn.commit()

    def remove_position(self, symbol: str):
        self.conn.execute("DELETE FROM portfolio WHERE symbol = ?", (symbol,))
        self.conn.commit()

    def get_positions(self) -> list[str]:
        rows = self.conn.execute("SELECT symbol FROM portfolio").fetchall()
        return [r["symbol"] for r in rows]

    def set_cooldown(self, symbol: str, alert_type: str, hours: int):
        expires = (datetime.now() + timedelta(hours=hours)).isoformat()
        self.conn.execute(
            "INSERT OR REPLACE INTO cooldowns (symbol, alert_type, expires_at) VALUES (?, ?, ?)",
            (symbol, alert_type, expires),
        )
        self.conn.commit()

    def is_on_cooldown(self, symbol: str, alert_type: str) -> bool:
        row = self.conn.execute(
            "SELECT expires_at FROM cooldowns WHERE symbol = ? AND alert_type = ?",
            (symbol, alert_type),
        ).fetchone()
        if not row:
            return False
        return datetime.fromisoformat(row["expires_at"]) > datetime.now()

    def close(self):
        self.conn.close()
