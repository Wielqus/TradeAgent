# market_data.py
import yfinance as yf
import pandas as pd
import logging

logger = logging.getLogger(__name__)


class MarketData:
    def get_price(self, symbol: str) -> float | None:
        try:
            ticker = yf.Ticker(symbol)
            price = ticker.fast_info.last_price
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
