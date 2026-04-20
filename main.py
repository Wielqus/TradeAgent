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
    import argparse

    parser = argparse.ArgumentParser(description="TradeAgent — Trading alerts Discord bot")
    parser.add_argument("--test-briefing", action="store_true", help="Send a test briefing and exit")
    parser.add_argument("--test-poll", action="store_true", help="Run one poll cycle and exit")
    args = parser.parse_args()

    agent = TradeAgent()

    if args.test_briefing:
        async def _test():
            await agent.bot.login(os.getenv("DISCORD_BOT_TOKEN"))
            await agent.morning_briefing()
            await agent.bot.close()
        asyncio.run(_test())
    elif args.test_poll:
        async def _test():
            await agent.bot.login(os.getenv("DISCORD_BOT_TOKEN"))
            await agent.poll_prices()
            await agent.bot.close()
        asyncio.run(_test())
    else:
        asyncio.run(agent.run())


if __name__ == "__main__":
    main()
