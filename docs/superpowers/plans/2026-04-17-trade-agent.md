# TradeAgent Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a trading agent that delivers daily briefings and real-time alerts on Discord for precious metals CFD and dynamically tracked stocks, using technical analysis + Claude CLI for natural language insights.

**Architecture:** Python pipeline polling Yahoo Finance every 2 min, computing TA indicators (pandas-ta), checking alert rules, and sending messages via Discord bot. Claude CLI (subprocess) generates human-friendly commentary. SQLite stores watchlist, portfolio, and cooldowns. APScheduler orchestrates timing.

**Tech Stack:** Python 3.12, yfinance, pandas-ta, discord.py, APScheduler, SQLite, Claude CLI (subprocess)

**Yahoo Finance ticker symbols:** Gold: `GC=F`, Silver: `SI=F`, Platinum: `PL=F`, Palladium: `PA=F`, Stocks: standard tickers (e.g. `AAPL`, `NVDA`)

**Note:** yfinance does not support `4h` interval — resample from `1h` data.

---

### Task 1: Project setup and dependencies

**Files:**
- Create: `requirements.txt`
- Create: `config.yaml`
- Create: `.env.example`
- Create: `.gitignore`

- [ ] **Step 1: Create requirements.txt**

```
yfinance>=0.2.36
pandas-ta>=0.3.14b1
discord.py>=2.3.2
APScheduler>=3.10.4
python-dotenv>=1.0.1
pyyaml>=6.0.1
aiohttp>=3.9.0
```

- [ ] **Step 2: Create .gitignore**

```
.env
__pycache__/
*.pyc
*.db
.venv/
```

- [ ] **Step 3: Create .env.example**

```
DISCORD_BOT_TOKEN=your_discord_bot_token_here
DISCORD_ALERTS_CHANNEL_ID=123456789
DISCORD_BRIEFING_CHANNEL_ID=123456789
DISCORD_CHAT_CHANNEL_ID=123456789
```

- [ ] **Step 4: Create config.yaml**

```yaml
# Yahoo Finance ticker symbols
default_watchlist:
  - symbol: "GC=F"
    name: "GOLD"
  - symbol: "SI=F"
    name: "SILVER"
  - symbol: "PL=F"
    name: "PLATINUM"
  - symbol: "PA=F"
    name: "PALLADIUM"

screener_symbols:
  - "AAPL"
  - "MSFT"
  - "GOOGL"
  - "AMZN"
  - "NVDA"
  - "TSLA"
  - "META"
  - "NFLX"
  - "AMD"
  - "INTC"
  - "JPM"
  - "GS"
  - "BA"
  - "DIS"
  - "NKE"
  - "KO"
  - "PFE"
  - "XOM"
  - "CVX"
  - "WMT"

alerts:
  rsi_extreme:
    enabled: true
    overbought: 70
    oversold: 30
    timeframes: ["4h", "1d"]
    cooldown_hours: 4
  ma_cross:
    enabled: true
    fast: 20
    slow: 50
    timeframes: ["1d"]
    cooldown_hours: 8
  macd_cross:
    enabled: true
    timeframes: ["4h", "1d"]
    cooldown_hours: 4
  bb_breakout:
    enabled: true
    timeframes: ["4h"]
    cooldown_hours: 4
  portfolio_change:
    enabled: true
    threshold_pct: 3.0
    cooldown_hours: 4

schedule:
  poll_interval_minutes: 2
  market_hours_start: 8   # CET
  market_hours_end: 22    # CET
  briefing_time: "07:30"
  screener_time: "07:00"
```

- [ ] **Step 5: Create virtual env and install dependencies**

Run: `python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt`

- [ ] **Step 6: Commit**

```bash
git add requirements.txt config.yaml .env.example .gitignore
git commit -m "feat: project setup with dependencies and config"
```

---

### Task 2: Database layer (db.py)

**Files:**
- Create: `db.py`
- Create: `tests/test_db.py`

- [ ] **Step 1: Write failing tests for database**

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `source .venv/bin/activate && python -m pytest tests/test_db.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'db'`

- [ ] **Step 3: Implement db.py**

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `source .venv/bin/activate && python -m pytest tests/test_db.py -v`
Expected: All 8 tests PASS

- [ ] **Step 5: Commit**

```bash
git add db.py tests/test_db.py
git commit -m "feat: database layer for watchlist, portfolio, and cooldowns"
```

---

### Task 3: Market data module (market_data.py)

**Files:**
- Create: `market_data.py`
- Create: `tests/test_market_data.py`

- [ ] **Step 1: Write failing tests**

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `source .venv/bin/activate && python -m pytest tests/test_market_data.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'market_data'`

- [ ] **Step 3: Implement market_data.py**

```python
# market_data.py
import yfinance as yf
import pandas as pd
import logging

logger = logging.getLogger(__name__)


class MarketData:
    def get_price(self, symbol: str) -> float | None:
        try:
            ticker = yf.Ticker(symbol)
            price = ticker.fast_info.get("last_price")
            return float(price) if price else None
        except Exception as e:
            logger.warning(f"Failed to get price for {symbol}: {e}")
            return None

    def get_prices(self, symbols: list[str]) -> dict[str, float | None]:
        return {s: self.get_price(s) for s in symbols}

    def get_candles(
        self, symbol: str, interval: str = "1d", period: str = "60d"
    ) -> pd.DataFrame | None:
        try:
            # yfinance doesn't support 4h — fetch 1h and resample
            if interval == "4h":
                df = yf.download(symbol, period=period, interval="1h", progress=False)
                if df.empty:
                    return None
                # Flatten MultiIndex columns if present
                if isinstance(df.columns, pd.MultiIndex):
                    df.columns = df.columns.get_level_values(0)
                df = (
                    df.resample("4h")
                    .agg({
                        "Open": "first",
                        "High": "max",
                        "Low": "min",
                        "Close": "last",
                        "Volume": "sum",
                    })
                    .dropna()
                )
                return df

            df = yf.download(symbol, period=period, interval=interval, progress=False)
            if df.empty:
                return None
            # Flatten MultiIndex columns if present
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            return df
        except Exception as e:
            logger.warning(f"Failed to get candles for {symbol} ({interval}): {e}")
            return None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `source .venv/bin/activate && python -m pytest tests/test_market_data.py -v`
Expected: All 6 tests PASS (requires internet)

- [ ] **Step 5: Commit**

```bash
git add market_data.py tests/test_market_data.py
git commit -m "feat: market data module using Yahoo Finance"
```

---

### Task 4: Signal Engine (signal_engine.py)

**Files:**
- Create: `signal_engine.py`
- Create: `tests/test_signal_engine.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_signal_engine.py
import pytest
import pandas as pd
import numpy as np
from signal_engine import SignalEngine


def make_candles(n=200, trend="up"):
    """Generate fake OHLCV data for testing."""
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
        assert "MACD_12_26_9" in result.columns
        assert "EMA_20" in result.columns
        assert "EMA_50" in result.columns
        assert "EMA_200" in result.columns
        assert "BBU_20_2.0" in result.columns
        assert "ATRr_14" in result.columns

    def test_compute_indicators_values_not_all_nan(self, engine):
        df = make_candles(200)
        result = engine.compute_indicators(df)
        assert result["RSI_14"].dropna().shape[0] > 0
        assert result["EMA_200"].dropna().shape[0] > 0


class TestAlertDetection:
    def test_detect_rsi_oversold(self, engine):
        df = make_candles(200)
        result = engine.compute_indicators(df)
        # Force RSI to oversold
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
        # Force golden cross: EMA20 crosses above EMA50
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
        # Force neutral values
        result.loc[result.index[-1], "RSI_14"] = 50.0
        result.loc[result.index[-2], "EMA_20"] = 100.0
        result.loc[result.index[-2], "EMA_50"] = 95.0
        result.loc[result.index[-1], "EMA_20"] = 101.0
        result.loc[result.index[-1], "EMA_50"] = 96.0
        # Force MACD no cross
        result.loc[result.index[-2], "MACD_12_26_9"] = 1.0
        result.loc[result.index[-2], "MACDs_12_26_9"] = 0.5
        result.loc[result.index[-1], "MACD_12_26_9"] = 1.1
        result.loc[result.index[-1], "MACDs_12_26_9"] = 0.6
        # Force price inside BB
        result.loc[result.index[-1], "BBU_20_2.0"] = 2500.0
        result.loc[result.index[-1], "BBL_20_2.0"] = 1500.0
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `source .venv/bin/activate && python -m pytest tests/test_signal_engine.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'signal_engine'`

- [ ] **Step 3: Implement signal_engine.py**

```python
# signal_engine.py
import pandas as pd
import pandas_ta as ta
import yaml
import logging

logger = logging.getLogger(__name__)


def load_alert_config() -> dict:
    try:
        with open("config.yaml") as f:
            return yaml.safe_load(f).get("alerts", {})
    except FileNotFoundError:
        return {}


class SignalEngine:
    def __init__(self, config: dict | None = None):
        self.config = config or load_alert_config()

    def compute_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        df.ta.rsi(length=14, append=True)
        df.ta.macd(fast=12, slow=26, signal=9, append=True)
        df.ta.ema(length=20, append=True)
        df.ta.ema(length=50, append=True)
        df.ta.ema(length=200, append=True)
        df.ta.bbands(length=20, std=2, append=True)
        df.ta.atr(length=14, append=True)
        return df

    def check_alerts(self, symbol: str, df: pd.DataFrame, timeframe: str) -> list[dict]:
        alerts = []
        if len(df) < 2:
            return alerts
        last = df.iloc[-1]
        prev = df.iloc[-2]

        # RSI extreme
        cfg = self.config.get("rsi_extreme", {})
        if cfg.get("enabled", True) and timeframe in cfg.get("timeframes", ["4h", "1d"]):
            rsi = last.get("RSI_14")
            if rsi is not None and not pd.isna(rsi):
                if rsi < cfg.get("oversold", 30):
                    alerts.append({
                        "type": "rsi_extreme",
                        "symbol": symbol,
                        "timeframe": timeframe,
                        "direction": "oversold",
                        "value": round(rsi, 1),
                    })
                elif rsi > cfg.get("overbought", 70):
                    alerts.append({
                        "type": "rsi_extreme",
                        "symbol": symbol,
                        "timeframe": timeframe,
                        "direction": "overbought",
                        "value": round(rsi, 1),
                    })

        # MA cross
        cfg = self.config.get("ma_cross", {})
        if cfg.get("enabled", True) and timeframe in cfg.get("timeframes", ["1d"]):
            fast_key = f"EMA_{cfg.get('fast', 20)}"
            slow_key = f"EMA_{cfg.get('slow', 50)}"
            if fast_key in last.index and slow_key in last.index:
                curr_fast, curr_slow = last[fast_key], last[slow_key]
                prev_fast, prev_slow = prev[fast_key], prev[slow_key]
                if not any(pd.isna(v) for v in [curr_fast, curr_slow, prev_fast, prev_slow]):
                    if prev_fast <= prev_slow and curr_fast > curr_slow:
                        alerts.append({
                            "type": "ma_cross",
                            "symbol": symbol,
                            "timeframe": timeframe,
                            "direction": "golden_cross",
                        })
                    elif prev_fast >= prev_slow and curr_fast < curr_slow:
                        alerts.append({
                            "type": "ma_cross",
                            "symbol": symbol,
                            "timeframe": timeframe,
                            "direction": "death_cross",
                        })

        # MACD cross
        cfg = self.config.get("macd_cross", {})
        if cfg.get("enabled", True) and timeframe in cfg.get("timeframes", ["4h", "1d"]):
            macd_key, signal_key = "MACD_12_26_9", "MACDs_12_26_9"
            if macd_key in last.index and signal_key in last.index:
                cm, cs = last[macd_key], last[signal_key]
                pm, ps = prev[macd_key], prev[signal_key]
                if not any(pd.isna(v) for v in [cm, cs, pm, ps]):
                    if pm <= ps and cm > cs:
                        alerts.append({
                            "type": "macd_cross",
                            "symbol": symbol,
                            "timeframe": timeframe,
                            "direction": "bullish",
                        })
                    elif pm >= ps and cm < cs:
                        alerts.append({
                            "type": "macd_cross",
                            "symbol": symbol,
                            "timeframe": timeframe,
                            "direction": "bearish",
                        })

        # BB breakout
        cfg = self.config.get("bb_breakout", {})
        if cfg.get("enabled", True) and timeframe in cfg.get("timeframes", ["4h"]):
            close = last.get("Close")
            bbu = last.get("BBU_20_2.0")
            bbl = last.get("BBL_20_2.0")
            if close is not None and bbu is not None and bbl is not None:
                if not any(pd.isna(v) for v in [close, bbu, bbl]):
                    if close > bbu:
                        alerts.append({
                            "type": "bb_breakout",
                            "symbol": symbol,
                            "timeframe": timeframe,
                            "direction": "above",
                        })
                    elif close < bbl:
                        alerts.append({
                            "type": "bb_breakout",
                            "symbol": symbol,
                            "timeframe": timeframe,
                            "direction": "below",
                        })

        return alerts

    def get_summary(self, symbol: str, df: pd.DataFrame) -> dict:
        last = df.iloc[-1]
        price = last.get("Close", 0)
        rsi = last.get("RSI_14")
        ema20 = last.get("EMA_20")
        ema50 = last.get("EMA_50")
        ema200 = last.get("EMA_200")

        if ema20 is not None and ema50 is not None and not pd.isna(ema20) and not pd.isna(ema50):
            if ema20 > ema50:
                trend = "UP"
            elif ema20 < ema50:
                trend = "DOWN"
            else:
                trend = "FLAT"
        else:
            trend = "N/A"

        return {
            "symbol": symbol,
            "price": round(float(price), 2) if not pd.isna(price) else 0,
            "rsi": round(float(rsi), 1) if rsi is not None and not pd.isna(rsi) else None,
            "trend": trend,
            "ema20": round(float(ema20), 2) if ema20 is not None and not pd.isna(ema20) else None,
            "ema50": round(float(ema50), 2) if ema50 is not None and not pd.isna(ema50) else None,
            "ema200": round(float(ema200), 2) if ema200 is not None and not pd.isna(ema200) else None,
        }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `source .venv/bin/activate && python -m pytest tests/test_signal_engine.py -v`
Expected: All 7 tests PASS

- [ ] **Step 5: Commit**

```bash
git add signal_engine.py tests/test_signal_engine.py
git commit -m "feat: signal engine with TA indicators and alert rules"
```

---

### Task 5: Claude CLI integration (llm.py)

**Files:**
- Create: `llm.py`
- Create: `prompts/alert.txt`
- Create: `prompts/briefing.txt`
- Create: `prompts/chat.txt`
- Create: `tests/test_llm.py`

- [ ] **Step 1: Create prompt templates**

`prompts/alert.txt`:
```
Jesteś asystentem tradingowym. Dostajesz dane o alercie na instrumencie finansowym.
Napisz krótką, luźną wskazówkę po polsku (2-3 zdania). Mów prosto, jak kolega trader.
Używaj zwrotów: "rozważ", "uważaj", "poczekaj", "może rosnąć/spaść", "obserwuj".
NIE podawaj dokładnych poziomów wejścia, SL, TP.
NIE używaj żargonu finansowego.

Dane alertu:
{alert_data}
```

`prompts/briefing.txt`:
```
Jesteś asystentem tradingowym. Dostajesz podsumowanie portfela i watchlisty.
Napisz krótki komentarz na koniec briefingu (2-3 zdania). Po polsku, prosto.
Skup się na najważniejszej rzeczy — co warto obserwować dziś.

Dane:
{briefing_data}
```

`prompts/chat.txt`:
```
Jesteś asystentem tradingowym na Discordzie. Odpowiadasz na pytania po polsku, krótko i prosto.
Masz dostęp do aktualnych danych rynkowych i portfela użytkownika.

Aktualne dane:
{context}

Pytanie użytkownika:
{question}
```

- [ ] **Step 2: Write failing tests**

```python
# tests/test_llm.py
import pytest
from unittest.mock import patch
from llm import generate_response


class TestLLM:
    @patch("llm.subprocess.run")
    def test_generate_response_returns_string(self, mock_run):
        mock_run.return_value = type("R", (), {"stdout": "Złoto rośnie.", "returncode": 0})()
        result = generate_response("test prompt")
        assert isinstance(result, str)
        assert len(result) > 0

    @patch("llm.subprocess.run")
    def test_generate_response_calls_claude(self, mock_run):
        mock_run.return_value = type("R", (), {"stdout": "OK", "returncode": 0})()
        generate_response("test prompt")
        mock_run.assert_called_once()
        args = mock_run.call_args
        assert "claude" in args[0][0] or "claude" in str(args)

    @patch("llm.subprocess.run")
    def test_generate_response_error_returns_fallback(self, mock_run):
        mock_run.side_effect = Exception("CLI not found")
        result = generate_response("test prompt")
        assert isinstance(result, str)
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `source .venv/bin/activate && python -m pytest tests/test_llm.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'llm'`

- [ ] **Step 4: Implement llm.py**

```python
# llm.py
import subprocess
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

PROMPTS_DIR = Path(__file__).parent / "prompts"


def _load_template(name: str) -> str:
    path = PROMPTS_DIR / f"{name}.txt"
    return path.read_text()


def generate_response(prompt: str) -> str:
    try:
        result = subprocess.run(
            ["claude", "-p", prompt, "--model", "sonnet"],
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
        logger.warning(f"Claude CLI returned code {result.returncode}: {result.stderr}")
        return ""
    except Exception as e:
        logger.error(f"Claude CLI error: {e}")
        return ""


def generate_alert_comment(alert_data: str) -> str:
    template = _load_template("alert")
    prompt = template.replace("{alert_data}", alert_data)
    return generate_response(prompt)


def generate_briefing_comment(briefing_data: str) -> str:
    template = _load_template("briefing")
    prompt = template.replace("{briefing_data}", briefing_data)
    return generate_response(prompt)


def generate_chat_response(context: str, question: str) -> str:
    template = _load_template("chat")
    prompt = template.replace("{context}", context).replace("{question}", question)
    return generate_response(prompt)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `source .venv/bin/activate && python -m pytest tests/test_llm.py -v`
Expected: All 3 tests PASS

- [ ] **Step 6: Commit**

```bash
git add llm.py prompts/ tests/test_llm.py
git commit -m "feat: Claude CLI integration with prompt templates"
```

---

### Task 6: Discord bot (discord_bot.py)

**Files:**
- Create: `discord_bot.py`
- Create: `tests/test_discord_bot.py`

- [ ] **Step 1: Write failing tests for message parsing**

```python
# tests/test_discord_bot.py
import pytest
from discord_bot import parse_command


class TestParseCommand:
    def test_buy_command(self):
        result = parse_command("kupiłem złoto")
        assert result["action"] == "buy"
        assert result["symbol"] == "GOLD"

    def test_sell_command(self):
        result = parse_command("zamknąłem silver")
        assert result["action"] == "sell"
        assert result["symbol"] == "SILVER"

    def test_add_watchlist(self):
        result = parse_command("dodaj NVIDIA")
        assert result["action"] == "add_watchlist"
        assert result["symbol"] == "NVDA"

    def test_remove_watchlist(self):
        result = parse_command("usuń TESLA")
        assert result["action"] == "remove_watchlist"
        assert result["symbol"] == "TSLA"

    def test_regular_question(self):
        result = parse_command("co myślisz o złocie?")
        assert result["action"] == "question"
        assert result["text"] == "co myślisz o złocie?"

    def test_show_portfolio(self):
        result = parse_command("pokaż portfel")
        assert result["action"] == "show_portfolio"

    def test_show_watchlist(self):
        result = parse_command("pokaż watchlistę")
        assert result["action"] == "show_watchlist"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `source .venv/bin/activate && python -m pytest tests/test_discord_bot.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'discord_bot'`

- [ ] **Step 3: Implement discord_bot.py**

```python
# discord_bot.py
import os
import re
import logging
import discord
from discord.ext import commands
from db import Database
from llm import generate_chat_response
from market_data import MarketData
from signal_engine import SignalEngine

logger = logging.getLogger(__name__)

# Symbol aliases: user-friendly name -> Yahoo Finance ticker
SYMBOL_ALIASES = {
    "ZŁOTO": "GC=F", "GOLD": "GC=F", "ZLOTO": "GC=F",
    "SREBRO": "SI=F", "SILVER": "SI=F",
    "PLATYNA": "PL=F", "PLATINUM": "PL=F",
    "PALLAD": "PA=F", "PALLADIUM": "PA=F",
    "NVIDIA": "NVDA", "TESLA": "TSLA", "APPLE": "AAPL",
    "GOOGLE": "GOOGL", "AMAZON": "AMZN", "MICROSOFT": "MSFT",
}

# Display names: Yahoo ticker -> friendly name
DISPLAY_NAMES = {v: k for k, v in SYMBOL_ALIASES.items() if k == k.upper() and not k.startswith(("ZŁ", "ZL", "SR", "PL", "PA"))}
DISPLAY_NAMES.update({"GC=F": "GOLD", "SI=F": "SILVER", "PL=F": "PLATINUM", "PA=F": "PALLADIUM"})


def resolve_symbol(text: str) -> str:
    upper = text.strip().upper()
    return SYMBOL_ALIASES.get(upper, upper)


def parse_command(text: str) -> dict:
    lower = text.lower().strip()

    # Buy commands
    buy_patterns = [r"kupi[łl]em\s+(.+)", r"kupi[łl]am\s+(.+)", r"buy\s+(.+)"]
    for pattern in buy_patterns:
        m = re.match(pattern, lower)
        if m:
            return {"action": "buy", "symbol": resolve_symbol(m.group(1))}

    # Sell commands
    sell_patterns = [
        r"zamkn[ąa][łl]em\s+(.+)", r"zamkn[ęe][łl]am\s+(.+)",
        r"sprzeda[łl]em\s+(.+)", r"sell\s+(.+)",
    ]
    for pattern in sell_patterns:
        m = re.match(pattern, lower)
        if m:
            return {"action": "sell", "symbol": resolve_symbol(m.group(1))}

    # Watchlist add
    m = re.match(r"dodaj\s+(.+)", lower)
    if m:
        return {"action": "add_watchlist", "symbol": resolve_symbol(m.group(1))}

    # Watchlist remove
    m = re.match(r"usu[ńn]\s+(.+)", lower)
    if m:
        return {"action": "remove_watchlist", "symbol": resolve_symbol(m.group(1))}

    # Show portfolio
    if re.search(r"poka[żz]\s+portfel", lower):
        return {"action": "show_portfolio"}

    # Show watchlist
    if re.search(r"poka[żz]\s+watchlist", lower):
        return {"action": "show_watchlist"}

    # Default: question
    return {"action": "question", "text": text}


class TradeBot(commands.Bot):
    def __init__(self, db: Database, market: MarketData, engine: SignalEngine):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(command_prefix="!", intents=intents)
        self.db = db
        self.market = market
        self.engine = engine
        self.alerts_channel_id = int(os.getenv("DISCORD_ALERTS_CHANNEL_ID", "0"))
        self.briefing_channel_id = int(os.getenv("DISCORD_BRIEFING_CHANNEL_ID", "0"))
        self.chat_channel_id = int(os.getenv("DISCORD_CHAT_CHANNEL_ID", "0"))

    async def on_ready(self):
        logger.info(f"Bot logged in as {self.user}")

    async def on_message(self, message: discord.Message):
        if message.author == self.user:
            return
        if message.channel.id != self.chat_channel_id:
            return

        cmd = parse_command(message.content)
        response = await self._handle_command(cmd)
        await message.channel.send(response)

    async def _handle_command(self, cmd: dict) -> str:
        action = cmd["action"]

        if action == "buy":
            symbol = cmd["symbol"]
            self.db.add_position(symbol)
            self.db.add_watchlist(symbol, source="portfolio")
            name = DISPLAY_NAMES.get(symbol, symbol)
            price = self.market.get_price(symbol)
            price_str = f" Cena: {price:.2f}" if price else ""
            return f"Dodano {name} do portfela.{price_str}"

        elif action == "sell":
            symbol = cmd["symbol"]
            self.db.remove_position(symbol)
            self.db.expire_watchlist(symbol, days=7)
            name = DISPLAY_NAMES.get(symbol, symbol)
            return f"Usunięto {name} z portfela. Zostaje na watchliście 7 dni."

        elif action == "add_watchlist":
            symbol = cmd["symbol"]
            self.db.add_watchlist(symbol, source="manual")
            name = DISPLAY_NAMES.get(symbol, symbol)
            price = self.market.get_price(symbol)
            price_str = f" Cena: {price:.2f}" if price else ""
            return f"Dodano {name} do watchlisty.{price_str}"

        elif action == "remove_watchlist":
            symbol = cmd["symbol"]
            self.db.remove_watchlist(symbol)
            name = DISPLAY_NAMES.get(symbol, symbol)
            return f"Usunięto {name} z watchlisty."

        elif action == "show_portfolio":
            positions = self.db.get_positions()
            if not positions:
                return "Portfel pusty."
            lines = []
            for sym in positions:
                name = DISPLAY_NAMES.get(sym, sym)
                price = self.market.get_price(sym)
                price_str = f" — {price:.2f}" if price else ""
                lines.append(f"• {name}{price_str}")
            return "PORTFEL:\n" + "\n".join(lines)

        elif action == "show_watchlist":
            items = self.db.get_watchlist()
            if not items:
                return "Watchlista pusta."
            lines = []
            for item in items:
                sym = item["symbol"]
                name = DISPLAY_NAMES.get(sym, sym)
                src = item["source"]
                lines.append(f"• {name} ({src})")
            return "WATCHLISTA:\n" + "\n".join(lines)

        elif action == "question":
            context = self._build_context()
            return generate_chat_response(context, cmd["text"])

        return "Nie rozumiem. Spróbuj: 'kupiłem złoto', 'dodaj NVIDIA', 'pokaż portfel'."

    def _build_context(self) -> str:
        positions = self.db.get_positions()
        watchlist = self.db.get_watchlist()
        symbols = list(set(positions + [w["symbol"] for w in watchlist]))

        lines = [f"Portfel: {', '.join(DISPLAY_NAMES.get(s, s) for s in positions) or 'pusty'}"]
        for sym in symbols[:10]:  # limit to avoid huge context
            price = self.market.get_price(sym)
            name = DISPLAY_NAMES.get(sym, sym)
            if price:
                lines.append(f"{name}: {price:.2f}")
        return "\n".join(lines)

    async def send_alert(self, text: str):
        channel = self.get_channel(self.alerts_channel_id)
        if channel:
            await channel.send(text)

    async def send_briefing(self, text: str):
        channel = self.get_channel(self.briefing_channel_id)
        if channel:
            await channel.send(text)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `source .venv/bin/activate && python -m pytest tests/test_discord_bot.py -v`
Expected: All 7 tests PASS

- [ ] **Step 5: Commit**

```bash
git add discord_bot.py tests/test_discord_bot.py
git commit -m "feat: Discord bot with command parsing and portfolio tracking"
```

---

### Task 7: Screener (screener.py)

**Files:**
- Create: `screener.py`
- Create: `tests/test_screener.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_screener.py
import pytest
from unittest.mock import MagicMock, patch
import pandas as pd
import numpy as np
from screener import Screener


def make_candles(n=200, rsi_final=50.0):
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `source .venv/bin/activate && python -m pytest tests/test_screener.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'screener'`

- [ ] **Step 3: Implement screener.py**

```python
# screener.py
import logging
import yaml
from market_data import MarketData
from signal_engine import SignalEngine

logger = logging.getLogger(__name__)


def load_screener_symbols() -> list[str]:
    try:
        with open("config.yaml") as f:
            return yaml.safe_load(f).get("screener_symbols", [])
    except FileNotFoundError:
        return []


class Screener:
    def __init__(
        self,
        market: MarketData,
        engine: SignalEngine,
        symbols: list[str] | None = None,
    ):
        self.market = market
        self.engine = engine
        self.symbols = symbols or load_screener_symbols()

    def scan(self) -> list[dict]:
        opportunities = []
        for symbol in self.symbols:
            try:
                df = self.market.get_candles(symbol, interval="1d", period="60d")
                if df is None or len(df) < 50:
                    continue
                df = self.engine.compute_indicators(df)
                summary = self.engine.get_summary(symbol, df)
                rsi = summary.get("rsi")
                if rsi is not None and rsi < 30:
                    opportunities.append({
                        "symbol": symbol,
                        "reason": "oversold",
                        "rsi": rsi,
                        "price": summary["price"],
                        "trend": summary["trend"],
                    })
                elif rsi is not None and rsi > 70:
                    opportunities.append({
                        "symbol": symbol,
                        "reason": "overbought",
                        "rsi": rsi,
                        "price": summary["price"],
                        "trend": summary["trend"],
                    })
            except Exception as e:
                logger.warning(f"Screener error for {symbol}: {e}")
        return opportunities
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `source .venv/bin/activate && python -m pytest tests/test_screener.py -v`
Expected: All 3 tests PASS

- [ ] **Step 5: Commit**

```bash
git add screener.py tests/test_screener.py
git commit -m "feat: screener for finding stock opportunities"
```

---

### Task 8: Main orchestrator (main.py)

**Files:**
- Create: `main.py`

- [ ] **Step 1: Implement main.py**

```python
# main.py
import os
import asyncio
import logging
from datetime import datetime
from zoneinfo import ZoneInfo

import yaml
from dotenv import load_dotenv
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger

from db import Database
from market_data import MarketData
from signal_engine import SignalEngine
from screener import Screener
from discord_bot import TradeBot, DISPLAY_NAMES
from llm import generate_alert_comment, generate_briefing_comment

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

CET = ZoneInfo("Europe/Warsaw")


def load_config() -> dict:
    with open("config.yaml") as f:
        return yaml.safe_load(f)


class TradeAgent:
    def __init__(self):
        self.config = load_config()
        self.db = Database()
        self.market = MarketData()
        self.engine = SignalEngine(self.config.get("alerts", {}))
        self.screener = Screener(self.market, self.engine)
        self.bot = TradeBot(self.db, self.market, self.engine)
        self.scheduler = AsyncIOScheduler(timezone=CET)

        # Initialize default watchlist
        for item in self.config.get("default_watchlist", []):
            self.db.add_watchlist(item["symbol"], source="default")

    def _is_market_hours(self) -> bool:
        now = datetime.now(CET)
        start = self.config["schedule"]["market_hours_start"]
        end = self.config["schedule"]["market_hours_end"]
        if now.weekday() >= 5:  # Saturday, Sunday
            return False
        return start <= now.hour < end

    async def poll_prices(self):
        if not self._is_market_hours():
            return

        watchlist = self.db.get_watchlist()
        positions = self.db.get_positions()
        symbols = list(set([w["symbol"] for w in watchlist] + positions))

        for symbol in symbols:
            for timeframe in ["4h", "1d"]:
                period = "7d" if timeframe == "4h" else "60d"
                df = self.market.get_candles(symbol, interval=timeframe, period=period)
                if df is None or len(df) < 20:
                    continue
                df = self.engine.compute_indicators(df)
                alerts = self.engine.check_alerts(symbol, df, timeframe)

                for alert in alerts:
                    alert_key = f"{symbol}_{alert['type']}"
                    if self.db.is_on_cooldown(symbol, alert['type']):
                        continue

                    name = DISPLAY_NAMES.get(symbol, symbol)
                    summary = self.engine.get_summary(symbol, df)
                    alert_data = f"Symbol: {name}, Alert: {alert['type']}, Direction: {alert.get('direction', '')}, RSI: {summary.get('rsi')}, Trend: {summary.get('trend')}, Price: {summary.get('price')}"
                    comment = generate_alert_comment(alert_data)

                    msg = f"🔔 {name} — warto obserwować\n\n{comment}"
                    await self.bot.send_alert(msg)

                    cooldown_cfg = self.config.get("alerts", {}).get(alert["type"], {})
                    cooldown_hours = cooldown_cfg.get("cooldown_hours", 4)
                    self.db.set_cooldown(symbol, alert["type"], hours=cooldown_hours)
                    logger.info(f"Alert sent: {name} {alert['type']} {alert.get('direction', '')}")

    async def morning_briefing(self):
        positions = self.db.get_positions()
        watchlist = self.db.get_watchlist()

        today = datetime.now(CET).strftime("%d.%m.%Y")
        lines = [f"📋 BRIEFING {today}\n"]

        # Portfolio section
        if positions:
            pos_parts = []
            for sym in positions:
                name = DISPLAY_NAMES.get(sym, sym)
                price = self.market.get_price(sym)
                pos_parts.append(f"{name}" + (f" {price:.2f}" if price else ""))
            lines.append("PORTFEL: " + " | ".join(pos_parts))
            lines.append("")

        # Watchlist section
        symbols = list(set([w["symbol"] for w in watchlist]))
        for sym in symbols:
            df = self.market.get_candles(sym, interval="1d", period="60d")
            if df is None or len(df) < 20:
                continue
            df = self.engine.compute_indicators(df)
            summary = self.engine.get_summary(sym, df)
            name = DISPLAY_NAMES.get(sym, sym)
            trend = summary["trend"]
            rsi = summary.get("rsi", "N/A")
            emoji = "🟢" if trend == "UP" else "🔴" if trend == "DOWN" else "🟡"
            lines.append(f"{emoji} {name} — trend {trend}, RSI {rsi}")

        # Opportunities
        opps = self.screener.scan()
        if opps:
            lines.append("\nOKAZJE:")
            for opp in opps[:5]:
                name = DISPLAY_NAMES.get(opp["symbol"], opp["symbol"])
                lines.append(f"• {name} — RSI {opp['rsi']}, {opp['reason']}")

        briefing_data = "\n".join(lines)
        comment = generate_briefing_comment(briefing_data)
        if comment:
            lines.append(f"\n{comment}")

        msg = "\n".join(lines)
        await self.bot.send_briefing(msg)
        logger.info("Morning briefing sent")

    async def run(self):
        poll_interval = self.config["schedule"]["poll_interval_minutes"]
        self.scheduler.add_job(
            self.poll_prices,
            IntervalTrigger(minutes=poll_interval),
            id="poll_prices",
        )

        briefing_time = self.config["schedule"]["briefing_time"]
        hour, minute = briefing_time.split(":")
        self.scheduler.add_job(
            self.morning_briefing,
            CronTrigger(hour=int(hour), minute=int(minute)),
            id="morning_briefing",
        )

        self.scheduler.start()
        token = os.getenv("DISCORD_BOT_TOKEN")
        await self.bot.start(token)


def main():
    agent = TradeAgent()
    asyncio.run(agent.run())


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Verify syntax**

Run: `source .venv/bin/activate && python -c "import ast; ast.parse(open('main.py').read()); print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add main.py
git commit -m "feat: main orchestrator with APScheduler and polling"
```

---

### Task 9: Systemd service and deployment

**Files:**
- Create: `tradeagent.service`

- [ ] **Step 1: Create systemd service file**

```ini
[Unit]
Description=TradeAgent — Trading alerts Discord bot
After=network.target

[Service]
Type=simple
User=wielqus
WorkingDirectory=/home/wielqus/TradeAgent
ExecStart=/home/wielqus/TradeAgent/.venv/bin/python main.py
Restart=always
RestartSec=10
EnvironmentFile=/home/wielqus/TradeAgent/.env

[Install]
WantedBy=multi-user.target
```

- [ ] **Step 2: Create .env from example**

Run: `cp .env.example .env` then edit `.env` with actual Discord bot token and channel IDs.

- [ ] **Step 3: Commit**

```bash
git add tradeagent.service
git commit -m "feat: systemd service for VPS deployment"
```

- [ ] **Step 4: Deploy instructions**

To deploy on VPS:
```bash
# Copy service file
sudo cp tradeagent.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable tradeagent
sudo systemctl start tradeagent

# Check status
sudo systemctl status tradeagent

# View logs
journalctl -u tradeagent -f
```

---

### Task 10: Integration test — end-to-end smoke test

**Files:**
- Create: `tests/test_integration.py`

- [ ] **Step 1: Write integration test**

```python
# tests/test_integration.py
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from db import Database
from market_data import MarketData
from signal_engine import SignalEngine
from screener import Screener
from discord_bot import TradeBot, parse_command


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
```

- [ ] **Step 2: Run integration tests**

Run: `source .venv/bin/activate && python -m pytest tests/test_integration.py -v`
Expected: All 4 tests PASS (requires internet)

- [ ] **Step 3: Run all tests**

Run: `source .venv/bin/activate && python -m pytest tests/ -v`
Expected: All tests PASS

- [ ] **Step 4: Commit**

```bash
git add tests/test_integration.py
git commit -m "feat: integration tests for end-to-end flow"
```
