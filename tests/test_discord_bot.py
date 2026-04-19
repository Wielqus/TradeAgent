import pytest
from discord_bot import parse_command


class TestParseCommand:
    def test_buy_command(self):
        result = parse_command("kupiłem złoto")
        assert result["action"] == "buy"
        assert result["symbol"] == "GC=F"

    def test_sell_command(self):
        result = parse_command("zamknąłem silver")
        assert result["action"] == "sell"
        assert result["symbol"] == "SI=F"

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
