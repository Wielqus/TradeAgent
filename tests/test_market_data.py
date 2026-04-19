# tests/test_market_data.py
import pytest
import pandas as pd
from market_data import MarketData


@pytest.fixture
def market():
    return MarketData()


class TestMarketData:
    def test_get_price_returns_float(self, market):
        price = market.get_price("GC=F")
        assert isinstance(price, float)
        assert price > 0

    def test_get_candles_1d(self, market):
        df = market.get_candles("GC=F", interval="1d", period="30d")
        assert isinstance(df, pd.DataFrame)
        assert len(df) > 0
        assert "Close" in df.columns

    def test_get_candles_1h(self, market):
        df = market.get_candles("GC=F", interval="1h", period="7d")
        assert isinstance(df, pd.DataFrame)
        assert len(df) > 0

    def test_get_candles_4h_resampled(self, market):
        df = market.get_candles("GC=F", interval="4h", period="7d")
        assert isinstance(df, pd.DataFrame)
        assert len(df) > 0

    def test_invalid_symbol_returns_none(self, market):
        price = market.get_price("INVALID_SYMBOL_XYZ123")
        assert price is None

    def test_get_multiple_prices(self, market):
        prices = market.get_prices(["GC=F", "SI=F"])
        assert "GC=F" in prices
        assert "SI=F" in prices
