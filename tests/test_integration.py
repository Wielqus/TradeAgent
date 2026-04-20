# tests/test_integration.py
import pytest
from db import Database
from market_data import MarketData
from signal_engine import SignalEngine
from screener import Screener
from discord_bot import parse_command


@pytest.fixture
def db(tmp_path):
    d = Database(str(tmp_path / "test.db"))
    yield d
    d.close()


class TestIntegration:
    def test_full_flow_add_position_and_check_watchlist(self, db):
        """User says 'kupiłem złoto' -> portfolio + watchlist updated."""
        cmd = parse_command("kupiłem złoto")
        assert cmd["action"] == "buy"
        assert cmd["symbol"] == "GC=F"
        db.add_position(cmd["symbol"])
        db.add_watchlist(cmd["symbol"], source="portfolio")
        assert "GC=F" in db.get_positions()
        assert any(w["symbol"] == "GC=F" for w in db.get_watchlist())

    def test_full_flow_sell_and_expire(self, db):
        """User says 'zamknąłem silver' -> removed from portfolio, watchlist expires."""
        db.add_position("SI=F")
        db.add_watchlist("SI=F", source="portfolio")
        cmd = parse_command("zamknąłem silver")
        assert cmd["action"] == "sell"
        db.remove_position(cmd["symbol"])
        db.expire_watchlist(cmd["symbol"], days=7)
        assert "SI=F" not in db.get_positions()
        watchlist = db.get_watchlist()
        item = [w for w in watchlist if w["symbol"] == "SI=F"][0]
        assert item["expires_at"] is not None

    def test_signal_engine_with_real_data(self):
        """Fetch real gold data and compute indicators."""
        market = MarketData()
        engine = SignalEngine()
        df = market.get_candles("GC=F", interval="1d", period="60d")
        assert df is not None
        df = engine.compute_indicators(df)
        summary = engine.get_summary("GC=F", df)
        assert summary["symbol"] == "GC=F"
        assert summary["price"] > 0
        assert summary["rsi"] is not None

    def test_screener_with_real_data(self):
        """Scan a few real stocks."""
        market = MarketData()
        engine = SignalEngine()
        screener = Screener(market, engine, symbols=["AAPL", "MSFT"])
        results = screener.scan()
        assert isinstance(results, list)
