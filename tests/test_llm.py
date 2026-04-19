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
