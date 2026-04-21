import pytest
import pandas as pd
import numpy as np
from signal_engine import SignalEngine


def make_candles(n=200, trend="up"):
    dates = pd.date_range("2026-01-01", periods=n, freq="1D")
    if trend == "up":
        close = 2000 + np.cumsum(np.random.randn(n) * 5 + 1)
    elif trend == "down":
        close = 2000 + np.cumsum(np.random.randn(n) * 5 - 1)
    else:
        close = 2000 + np.cumsum(np.random.randn(n) * 2)
    high = close + np.abs(np.random.randn(n) * 3)
    low = close - np.abs(np.random.randn(n) * 3)
    open_ = close + np.random.randn(n) * 2
    volume = np.random.randint(1000, 10000, n).astype(float)
    return pd.DataFrame(
        {"Open": open_, "High": high, "Low": low, "Close": close, "Volume": volume},
        index=dates,
    )


@pytest.fixture
def engine():
    return SignalEngine()


class TestIndicators:
    def test_compute_indicators_adds_columns(self, engine):
        df = make_candles(200)
        result = engine.compute_indicators(df)
        assert "RSI_14" in result.columns
        assert "MACD" in result.columns
        assert "MACD_signal" in result.columns
        assert "EMA_20" in result.columns
        assert "EMA_50" in result.columns
        assert "EMA_200" in result.columns
        assert "BB_upper" in result.columns
        assert "BB_lower" in result.columns
        assert "ATR_14" in result.columns

    def test_compute_indicators_values_not_all_nan(self, engine):
        df = make_candles(200)
        result = engine.compute_indicators(df)
        assert result["RSI_14"].dropna().shape[0] > 0
        assert result["EMA_200"].dropna().shape[0] > 0


class TestAlertDetection:
    def test_detect_rsi_oversold(self, engine):
        df = make_candles(200)
        result = engine.compute_indicators(df)
        result.loc[result.index[-1], "RSI_14"] = 25.0
        alerts = engine.check_alerts("GOLD", result, "1d")
        rsi_alerts = [a for a in alerts if a["type"] == "rsi_extreme"]
        assert len(rsi_alerts) == 1
        assert rsi_alerts[0]["direction"] == "oversold"

    def test_detect_rsi_overbought(self, engine):
        df = make_candles(200)
        result = engine.compute_indicators(df)
        result.loc[result.index[-1], "RSI_14"] = 75.0
        alerts = engine.check_alerts("GOLD", result, "1d")
        rsi_alerts = [a for a in alerts if a["type"] == "rsi_extreme"]
        assert len(rsi_alerts) == 1
        assert rsi_alerts[0]["direction"] == "overbought"

    def test_detect_ma_cross_golden(self, engine):
        df = make_candles(200)
        result = engine.compute_indicators(df)
        result.loc[result.index[-2], "EMA_20"] = 100.0
        result.loc[result.index[-2], "EMA_50"] = 105.0
        result.loc[result.index[-1], "EMA_20"] = 106.0
        result.loc[result.index[-1], "EMA_50"] = 105.0
        alerts = engine.check_alerts("GOLD", result, "1d")
        ma_alerts = [a for a in alerts if a["type"] == "ma_cross"]
        assert len(ma_alerts) == 1
        assert ma_alerts[0]["direction"] == "golden_cross"

    def test_no_alerts_normal_conditions(self, engine):
        df = make_candles(200)
        result = engine.compute_indicators(df)
        result.loc[result.index[-1], "RSI_14"] = 50.0
        result.loc[result.index[-2], "EMA_20"] = 100.0
        result.loc[result.index[-2], "EMA_50"] = 95.0
        result.loc[result.index[-1], "EMA_20"] = 101.0
        result.loc[result.index[-1], "EMA_50"] = 96.0
        result.loc[result.index[-2], "MACD"] = 1.0
        result.loc[result.index[-2], "MACD_signal"] = 0.5
        result.loc[result.index[-1], "MACD"] = 1.1
        result.loc[result.index[-1], "MACD_signal"] = 0.6
        result.loc[result.index[-1], "BB_upper"] = 2500.0
        result.loc[result.index[-1], "BB_lower"] = 1500.0
        alerts = engine.check_alerts("GOLD", result, "1d")
        assert len(alerts) == 0


class TestSummary:
    def test_get_summary(self, engine):
        df = make_candles(200, trend="up")
        result = engine.compute_indicators(df)
        summary = engine.get_summary("GOLD", result)
        assert "symbol" in summary
        assert "price" in summary
        assert "rsi" in summary
        assert "trend" in summary
