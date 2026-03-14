"""Warp terminal adapter for ctx."""

from __future__ import annotations

import subprocess

from loadout.adapters.terminal.base import TerminalAdapter


class WarpAdapter(TerminalAdapter):
    """Adapter for Warp terminal on macOS."""

    @property
    def name(self) -> str:
        return "warp"

    def is_available(self) -> bool:
        result = subprocess.run(
            ["pgrep", "-x", "Warp"],
            capture_output=True,
        )
        return result.returncode == 0

    def get_open_dirs(self) -> list[str]:
        # Warp doesn't expose directories via AppleScript easily
        return []

    def open_in_dir(self, directory: str) -> bool:
        result = subprocess.run(
            ["open", "-a", "Warp", directory],
            capture_output=True,
        )
        return result.returncode == 0
