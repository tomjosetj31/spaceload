"""Kitty terminal adapter for ctx."""

from __future__ import annotations

import json
import shutil
import subprocess

from loadout.adapters.terminal.base import TerminalAdapter


class KittyAdapter(TerminalAdapter):
    """Adapter for the kitty terminal emulator."""

    @property
    def name(self) -> str:
        return "kitty"

    def is_available(self) -> bool:
        if shutil.which("kitty") is None:
            return False
        result = subprocess.run(
            ["pgrep", "-x", "kitty"],
            capture_output=True,
        )
        return result.returncode == 0

    def get_open_dirs(self) -> list[str]:
        try:
            result = subprocess.run(
                ["kitty", "@", "ls"],
                capture_output=True,
                text=True,
            )
            if result.returncode != 0:
                return []
            data = json.loads(result.stdout)
            dirs: list[str] = []
            for window in data:
                for tab in window.get("tabs", []):
                    for win in tab.get("windows", []):
                        cwd = win.get("cwd", "")
                        if cwd:
                            dirs.append(cwd)
            return dirs
        except Exception:
            return []

    def open_in_dir(self, directory: str) -> bool:
        result = subprocess.run(
            ["kitty", "--directory", directory],
            capture_output=True,
        )
        return result.returncode == 0
