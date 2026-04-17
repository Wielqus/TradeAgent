# tests/test_db.py
import os
import pytest
from db import Database


@pytest.fixture
def db(tmp_path):
    db_path = tmp_path / "test.db"
    d = Database(str(db_path))
    yield d
    d.close()


class TestWatchlist:
    def test_add_to_watchlist(self, db):
        db.add_watchlist("NVDA", source="manual")
        items = db.get_watchlist()
        assert any(w["symbol"] == "NVDA" for w in items)

    def test_add_duplicate_ignored(self, db):
        db.add_watchlist("NVDA", source="manual")
        db.add_watchlist("NVDA", source="manual")
        items = [w for w in db.get_watchlist() if w["symbol"] == "NVDA"]
        assert len(items) == 1

    def test_remove_from_watchlist(self, db):
        db.add_watchlist("NVDA", source="manual")
        db.remove_watchlist("NVDA")
        items = db.get_watchlist()
        assert not any(w["symbol"] == "NVDA" for w in items)

    def test_expire_sets_date(self, db):
        db.add_watchlist("NVDA", source="portfolio")
        db.expire_watchlist("NVDA", days=7)
        items = db.get_watchlist()
        item = [w for w in items if w["symbol"] == "NVDA"][0]
        assert item["expires_at"] is not None


class TestPortfolio:
    def test_add_position(self, db):
        db.add_position("GOLD")
        positions = db.get_positions()
        assert "GOLD" in positions

    def test_remove_position(self, db):
        db.add_position("GOLD")
        db.remove_position("GOLD")
        positions = db.get_positions()
        assert "GOLD" not in positions

    def test_remove_position_not_exists(self, db):
        db.remove_position("GOLD")  # should not raise


class TestCooldowns:
    def test_cooldown_not_active_initially(self, db):
        assert not db.is_on_cooldown("GOLD", "rsi_extreme")

    def test_set_and_check_cooldown(self, db):
        db.set_cooldown("GOLD", "rsi_extreme", hours=4)
        assert db.is_on_cooldown("GOLD", "rsi_extreme")
