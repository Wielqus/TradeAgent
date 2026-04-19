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
