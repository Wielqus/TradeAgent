# TradeAgent — Design Spec

## Cel

Agent tradingowy dostarczający codzienne wskazówki i alerty na Discord. Skupiony na CFD metale szlachetne + dynamiczna lista akcji/innych instrumentów. Ton komunikacji: prosty, luźny, jak kolega trader ("rozważ dokupienie", "uważaj, może spaść").

## Podejście

Hybrid: analiza techniczna (wskaźniki) jako baza + Claude CLI do interpretacji kontekstu (newsy, sentiment, makro) i generowania wiadomości w naturalnym języku.

Architektura: Python pipeline z pollingiem co 2 min + APScheduler + Discord bot.

## Architektura

```
┌─────────────┐     ┌──────────────────┐     ┌──────────────┐     ┌─────────────┐
│  XTB Client │────>│  Signal Engine    │────>│  Claude CLI  │────>│ Discord Bot │
│  (dane)     │     │  (TA + reguły)   │     │  (subprocess)│     │ (discord.py)│
└─────────────┘     └──────────────────┘     └──────────────┘     └─────────────┘
       │                                                                │
       v                                                                │
┌─────────────┐                                                         │
│  Portfolio   │────────────────────────────────────────────────────────-┘
│  Tracker     │  (sync instrumentów z XTB -> dynamiczna watchlista)
└─────────────┘
```

Moduły:

1. **Market Data** — Yahoo Finance (`yfinance`), pobiera świeczki (1H, 4H, 1D), bieżące ceny. Polling co 2 min w godzinach 8:00-22:00 CET.
2. **Signal Engine** — oblicza wskaźniki TA, sprawdza reguły alertów, generuje sygnały.
3. **Claude CLI** — `claude -p "..."` przez subprocess. Otrzymuje kontekst (wskaźniki, newsy) i generuje luźną wskazówkę.
4. **Discord Bot** — pełny bot (`discord.py`), wysyła alerty i briefingi, odpowiada na pytania użytkownika. Obsługuje też komendy portfela ("kupiłem złoto", "zamknąłem silver").
5. **Portfolio Tracker** — prosty tracking przez komendy Discord. Użytkownik informuje bota co kupił/sprzedał, bot zapisuje w SQLite i uwzględnia w briefingach.

Stack: Python 3.12, yfinance, pandas-ta, claude CLI (subprocess), discord.py, APScheduler, SQLite.

## Signal Engine — wskaźniki i reguły

### Wskaźniki

| Wskaźnik | Timeframe | Zastosowanie |
|----------|-----------|-------------|
| RSI (14) | 1H, 4H, 1D | Wykupienie/wyprzedanie (>70 / <30) |
| MACD (12,26,9) | 4H, 1D | Crossovery — zmiana trendu |
| EMA 20/50/200 | 1D | Trend direction + golden/death cross |
| Bollinger Bands (20,2) | 4H | Breakouty, squeeze |
| ATR (14) | 1D | Volatility |
| Poziomy S/R | 1D | Automatycznie z pivotów i ostatnich swingów |

### Reguły alertów

| Typ alertu | Warunek | Priorytet |
|------------|---------|-----------|
| MA Cross | EMA20 przecina EMA50 (golden/death cross) | Wysoki |
| RSI Extreme | RSI < 30 lub RSI > 70 na 4H | Średni |
| MACD Cross | Linia MACD przecina signal line | Średni |
| BB Breakout | Cena zamyka się poza Bollinger Bands | Średni |
| S/R Test | Cena dotyka kluczowego poziomu wsparcia/oporu | Wysoki |
| Portfolio alert | Pozycja w portfelu zyskuje/traci >3% | Wysoki |

Cooldown: po wysłaniu alertu dla danego instrumentu + typu, kolejny taki sam alert blokowany przez 4h (konfigurowalny w YAML).

### Konfiguracja (config.yaml)

```yaml
alerts:
  rsi_extreme:
    enabled: true
    overbought: 70
    oversold: 30
    timeframes: ["4H", "1D"]
    cooldown_hours: 4
  ma_cross:
    enabled: true
    fast: 20
    slow: 50
    timeframes: ["1D"]
    cooldown_hours: 8
```

## Format wiadomości Discord

### Alert

```
🔔 GOLD — warto obserwować

Golden cross na dziennym, dolar słabnie.
Złoto może rosnąć — rozważ dokupienie.
Uwaga na CPI w czwartek, może namieszać.
```

Ton: prosty polski, krótkie zdania, konkretne podpowiedzi ("rozważ", "uważaj", "poczekaj", "może rosnąć"). Bez żargonu.

### Poranny briefing

```
📋 BRIEFING 16.04.2026

PORTFEL: GOLD +1.2% | SILVER -0.4%

🟢 GOLD — rośnie stabilnie, trzymaj
🟡 SILVER — stoi w miejscu, poczekaj
🔴 PLATINUM — spada, uważaj

OKAZJE:
• TESLA — mocno spadła, może się odbić
• PALLADIUM — na ważnym wsparciu, obserwuj

DZIŚ: 14:30 CPI 🔴 | 16:00 Fed 🟡
Może być nerwowo na metalach po CPI.
```

### Bot interaktywny

Bot nasłuchuje na kanale `#pytania` i odpowiada na pytania z kontekstem (aktualne dane, portfel, ostatnie sygnały):

```
Ty:    "Co myślisz o shorcie na srebrze?"
Bot:   "Silver stoi w miejscu, BB squeeze na 4H. Poczekaj
        na wyraźny ruch, na razie nie ma setupu na short."

Ty:    "Dodaj NVIDIA do watchlisty"
Bot:   "Dodano NVDA. Cena $892, trend UP, RSI 61."
```

## Watchlista + Portfolio Tracker

### Stała lista (zawsze monitorowane)

- GOLD (XAUUSD)
- SILVER (XAGUSD)
- PLATINUM (XPTUSD)
- PALLADIUM (XPDUSD)

### Dynamiczna lista

- Prosty tracking przez Discord — "kupiłem złoto" dodaje do portfela i watchlisty
- "Zamknąłem silver" — usuwa z portfela, instrument zostaje na watchliście 7 dni
- Ręczne dodawanie/usuwanie do watchlisty przez bota ("dodaj NVIDIA", "usuń TESLA")

### Przechowywanie (SQLite)

```
watchlist:
  - symbol: TEXT
  - source: TEXT (portfolio | manual | default)
  - added_at: DATETIME
  - expires_at: DATETIME nullable
```

### Screener okazji

Raz dziennie (7:00 CET) skanuje ~50 popularnych akcji US + EU. Szuka ekstremalnych warunków (RSI < 30, duże spadki, test kluczowych poziomów). Wyniki trafiają do briefingu.

### Kalendarz ekonomiczny

Dane kalendarza (CPI, Fed, NFP itp.) pobierane z darmowego API — Forex Factory scraping lub Investing.com calendar API. Parsowane raz dziennie przed briefingiem i przekazywane do Claude CLI jako kontekst.

## Harmonogram

| Proces | Częstotliwość | Godziny | Opis |
|--------|--------------|---------|------|
| Price poller | Co 2 min | 8:00-22:00 CET | Ceny, wskaźniki, alerty |
| Portfolio tracking | Na żądanie | 24/7 | Przez komendy Discord |
| Morning briefing | Raz dziennie | 7:30 CET | Briefing na Discord |
| Screener okazji | Raz dziennie | 7:00 CET | Skan ~50 akcji |
| Discord bot | Non-stop | 24/7 | Odpowiedzi na pytania |

Weekendy: poller i sync wyłączone.

## Struktura projektu

```
TradeAgent/
├── config.yaml           # watchlista stała, parametry wskaźników, reguły alertów
├── .env                  # tokeny (XTB, Discord)
├── main.py               # punkt wejścia, APScheduler
├── market_data.py        # pobieranie danych z Yahoo Finance
├── signal_engine.py      # wskaźniki TA + reguły alertów
├── llm.py                # wywołanie claude CLI (subprocess)
├── discord_bot.py        # bot Discord (alerty + pytania)
├── portfolio.py          # sync portfela + watchlista
├── screener.py           # skanowanie okazji
├── db.py                 # SQLite
└── prompts/
    ├── alert.txt         # prompt template dla alertów
    ├── briefing.txt      # prompt template dla briefingu
    └── chat.txt          # prompt template dla odpowiedzi na pytania
```

## Deployment

- **VPS** z Python 3.12 + claude CLI (już zainstalowany)
- **Systemd service** (`tradeagent.service`) — auto-restart po crashu
- **Logi** — journalctl
- **RAM** — ~512MB wystarczy
- **Sekrety** — `.env` (XTB credentials, Discord bot token)
