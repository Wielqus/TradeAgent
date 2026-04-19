import pytest
from unittest.mock import MagicMock
import pandas as pd
import numpy as np
from screener import Screener


def make_candles(n=200):
    dates = pd.date_range("2026-01-01", periods=n, freq="1D")
    close = 100 + np.cumsum(np.random.randn(n) * 2)
    df = pd.DataFrame({
        "Open": close + np.random.randn(n),
        "High": close + abs(np.random.randn(n) * 2),
        "Low": close - abs(np.random.randn(n) * 2),
        "Close": close,
        "Volume": np.random.randint(1000, 10000, n).astype(float),
    }, index=dates)
    return df


class TestScreener:
    def test_scan_returns_list(self):
        market = MagicMock()
        market.get_candles.return_value = make_candles(200)
        engine = MagicMock()
        engine.compute_indicators.side_effect = lambda df: df
        engine.get_summary.return_value = {
            "symbol": "AAPL", "price": 150.0, "rsi": 25.0, "trend": "DOWN",
        }
        screener = Screener(market, engine, symbols=["AAPL"])
        results = screener.scan()
        assert isinstance(results, list)

    def test_scan_finds_oversold(self):
        market = MagicMock()
        market.get_candles.return_value = make_candles(200)
        engine = MagicMock()
        engine.compute_indicators.side_effect = lambda df: df
        engine.get_summary.return_value = {
            "symbol": "AAPL", "price": 150.0, "rsi": 25.0, "trend": "DOWN",
        }
        screener = Screener(market, engine, symbols=["AAPL"])
        results = screener.scan()
        assert len(results) >= 1
        assert results[0]["symbol"] == "AAPL"
        assert results[0]["reason"] == "oversold"

    def test_scan_skips_neutral(self):
        market = MagicMock()
        market.get_candles.return_value = make_candles(200)
        engine = MagicMock()
        engine.compute_indicators.side_effect = lambda df: df
        engine.get_summary.return_value = {
            "symbol": "AAPL", "price": 150.0, "rsi": 50.0, "trend": "UP",
        }
        screener = Screener(market, engine, symbols=["AAPL"])
        results = screener.scan()
        assert len(results) == 0
