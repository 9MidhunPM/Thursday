"""
Personality loader for Thursday Web.

Reads personality.txt and provides system prompt injection.
Extension point: swap for dynamic per-user personality profiles.
"""

from pathlib import Path
from config import PERSONALITY_FILE


class Personality:
    """Loads and caches the system personality prompt."""

    def __init__(self, filepath: Path = PERSONALITY_FILE) -> None:
        self._filepath = filepath
        self._text: str | None = None

    def load(self) -> str:
        if self._text is None:
            if not self._filepath.exists():
                raise FileNotFoundError(f"Personality file not found: {self._filepath}")
            self._text = self._filepath.read_text(encoding="utf-8").strip()
        return self._text

    def reload(self) -> str:
        self._text = None
        return self.load()

    def as_system_message(self) -> dict:
        return {"role": "system", "content": self.load()}
