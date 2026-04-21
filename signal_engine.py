# signal_engine.py
import logging
import pandas as pd
import ta

logger = logging.getLogger(__name__)

DEFAULT_CONFIG = {
    "rsi_extreme": {
        "enabled": True,
        "overbought": 70,
        "oversold": 30,
        "timeframes": ["4h", "1d"],
        "cooldown_hours": 4,
    },
    "ma_cross": {
        "enabled": True,
        "fast": 20,
        "slow": 50,
        "timeframes": ["1d"],
        "cooldown_hours": 8,
    },
    "macd_cross": {
        "enabled": True,
        "timeframes": ["4h", "1d"],
        "cooldown_hours": 4,
    },
    "bb_breakout": {
        "enabled": True,
        "timeframes": ["4h"],
        "cooldown_hours": 4,
    },
}


class SignalEngine:
    def __init__(self, config: dict | None = None):
        self.config = config if config is not None else DEFAULT_CONFIG

    # ------------------------------------------------------------------
    # Indicator computation
    # ------------------------------------------------------------------

    def compute_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Add technical indicator columns to the DataFrame and return it."""
        df = df.copy()
        close = df["Close"]
        high = df["High"]
        low = df["Low"]

        # RSI
        df["RSI_14"] = ta.momentum.RSIIndicator(close=close, window=14).rsi()

        # MACD
        macd_ind = ta.trend.MACD(
            close=close, window_slow=26, window_fast=12, window_sign=9
        )
        df["MACD"] = macd_ind.macd()
        df["MACD_signal"] = macd_ind.macd_signal()

        # EMAs
        df["EMA_20"] = ta.trend.EMAIndicator(close=close, window=20).ema_indicator()
        df["EMA_50"] = ta.trend.EMAIndicator(close=close, window=50).ema_indicator()
        df["EMA_200"] = ta.trend.EMAIndicator(close=close, window=200).ema_indicator()

        # Bollinger Bands
        bb = ta.volatility.BollingerBands(close=close, window=20, window_dev=2)
        df["BB_upper"] = bb.bollinger_hband()
        df["BB_lower"] = bb.bollinger_lband()

        # ATR
        df["ATR_14"] = ta.volatility.AverageTrueRange(
            high=high, low=low, close=close, window=14
        ).average_true_range()

        return df

    # ------------------------------------------------------------------
    # Alert detection
    # ------------------------------------------------------------------

    def check_alerts(
        self, symbol: str, df: pd.DataFrame, timeframe: str
    ) -> list[dict]:
        """Return a list of alert dicts for the latest bar in the DataFrame."""
        alerts: list[dict] = []

        if len(df) < 2:
            return alerts

        last = df.iloc[-1]
        prev = df.iloc[-2]

        # --- RSI extreme ---
        rsi_cfg = self.config.get("rsi_extreme", {})
        if rsi_cfg.get("enabled", True) and timeframe in rsi_cfg.get(
            "timeframes", ["4h", "1d"]
        ):
            rsi = last.get("RSI_14")
            if pd.notna(rsi):
                overbought = rsi_cfg.get("overbought", 70)
                oversold = rsi_cfg.get("oversold", 30)
                if rsi > overbought:
                    alerts.append(
                        {
                            "type": "rsi_extreme",
                            "symbol": symbol,
                            "timeframe": timeframe,
                            "direction": "overbought",
                            "value": float(rsi),
                        }
                    )
                elif rsi < oversold:
                    alerts.append(
                        {
                            "type": "rsi_extreme",
                            "symbol": symbol,
                            "timeframe": timeframe,
                            "direction": "oversold",
                            "value": float(rsi),
                        }
                    )

        # --- MA cross (EMA_20 vs EMA_50) ---
        ma_cfg = self.config.get("ma_cross", {})
        if ma_cfg.get("enabled", True) and timeframe in ma_cfg.get(
            "timeframes", ["1d"]
        ):
            ema20_now = last.get("EMA_20")
            ema50_now = last.get("EMA_50")
            ema20_prev = prev.get("EMA_20")
            ema50_prev = prev.get("EMA_50")
            if all(pd.notna(v) for v in [ema20_now, ema50_now, ema20_prev, ema50_prev]):
                # Golden cross: fast crosses above slow
                if ema20_prev <= ema50_prev and ema20_now > ema50_now:
                    alerts.append(
                        {
                            "type": "ma_cross",
                            "symbol": symbol,
                            "timeframe": timeframe,
                            "direction": "golden_cross",
                        }
                    )
                # Death cross: fast crosses below slow
                elif ema20_prev >= ema50_prev and ema20_now < ema50_now:
                    alerts.append(
                        {
                            "type": "ma_cross",
                            "symbol": symbol,
                            "timeframe": timeframe,
                            "direction": "death_cross",
                        }
                    )

        # --- MACD cross ---
        macd_cfg = self.config.get("macd_cross", {})
        if macd_cfg.get("enabled", True) and timeframe in macd_cfg.get(
            "timeframes", ["4h", "1d"]
        ):
            macd_now = last.get("MACD")
            sig_now = last.get("MACD_signal")
            macd_prev = prev.get("MACD")
            sig_prev = prev.get("MACD_signal")
            if all(pd.notna(v) for v in [macd_now, sig_now, macd_prev, sig_prev]):
                if macd_prev <= sig_prev and macd_now > sig_now:
                    alerts.append(
                        {
                            "type": "macd_cross",
                            "symbol": symbol,
                            "timeframe": timeframe,
                            "direction": "bullish",
                        }
                    )
                elif macd_prev >= sig_prev and macd_now < sig_now:
                    alerts.append(
                        {
                            "type": "macd_cross",
                            "symbol": symbol,
                            "timeframe": timeframe,
                            "direction": "bearish",
                        }
                    )

        # --- Bollinger Band breakout ---
        bb_cfg = self.config.get("bb_breakout", {})
        if bb_cfg.get("enabled", True) and timeframe in bb_cfg.get(
            "timeframes", ["4h"]
        ):
            close_now = last.get("Close")
            bb_upper = last.get("BB_upper")
            bb_lower = last.get("BB_lower")
            if all(pd.notna(v) for v in [close_now, bb_upper, bb_lower]):
                if close_now > bb_upper:
                    alerts.append(
                        {
                            "type": "bb_breakout",
                            "symbol": symbol,
                            "timeframe": timeframe,
                            "direction": "above_upper",
                            "value": float(close_now),
                        }
                    )
                elif close_now < bb_lower:
                    alerts.append(
                        {
                            "type": "bb_breakout",
                            "symbol": symbol,
                            "timeframe": timeframe,
                            "direction": "below_lower",
                            "value": float(close_now),
                        }
                    )

        return alerts

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------

    def get_summary(self, symbol: str, df: pd.DataFrame) -> dict:
        """Return a summary dict for the latest bar."""
        last = df.iloc[-1]

        price = float(last["Close"]) if pd.notna(last.get("Close")) else None
        rsi = float(last["RSI_14"]) if pd.notna(last.get("RSI_14")) else None
        ema20 = float(last["EMA_20"]) if pd.notna(last.get("EMA_20")) else None
        ema50 = float(last["EMA_50"]) if pd.notna(last.get("EMA_50")) else None
        ema200 = float(last["EMA_200"]) if pd.notna(last.get("EMA_200")) else None

        if ema20 is not None and ema50 is not None:
            diff_pct = (ema20 - ema50) / ema50 * 100
            if diff_pct > 0.5:
                trend = "UP"
            elif diff_pct < -0.5:
                trend = "DOWN"
            else:
                trend = "FLAT"
        else:
            trend = "FLAT"

        return {
            "symbol": symbol,
            "price": price,
            "rsi": rsi,
            "trend": trend,
            "ema20": ema20,
            "ema50": ema50,
            "ema200": ema200,
        }
