"""Token resolver — handles {{TOKEN}} replacement on import."""

from __future__ import annotations

import re
from pathlib import Path

_TOKEN_RE = re.compile(r"\{\{(\w+)\}\}")


def detect_tokens(text: str) -> set[str]:
    """Return all unique token names found in text."""
    return set(_TOKEN_RE.findall(text))


def auto_tokens() -> dict[str, str]:
    """Return tokens that can be resolved automatically (no user prompt needed)."""
    return {"HOME": str(Path.home())}


def resolve_tokens(text: str, token_values: dict[str, str]) -> str:
    """Replace all {{TOKEN}} placeholders with their values."""
    def _replace(match: re.Match) -> str:
        return token_values.get(match.group(1), match.group(0))

    return _TOKEN_RE.sub(_replace, text)
