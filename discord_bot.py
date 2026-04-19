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

DISPLAY_NAMES = {"GC=F": "GOLD", "SI=F": "SILVER", "PL=F": "PLATINUM", "PA=F": "PALLADIUM"}


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
        for sym in symbols[:10]:
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
