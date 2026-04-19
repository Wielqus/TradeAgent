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
