"""Terminal adapter registry for ctx."""

from __future__ import annotations

from loadout.adapters.terminal.iterm2 import ITerm2Adapter
from loadout.adapters.terminal.terminal_app import TerminalAppAdapter
from loadout.adapters.terminal.warp import WarpAdapter
from loadout.adapters.terminal.kitty import KittyAdapter


class TerminalAdapterRegistry:
    """Registry of all known terminal adapters."""

    def __init__(self) -> None:
        self._adapters = [
            ITerm2Adapter(),
            TerminalAppAdapter(),
            WarpAdapter(),
            KittyAdapter(),
        ]

    def available_adapters(self) -> list:
        """Return adapters whose terminal app is currently running."""
        return [a for a in self._adapters if a.is_available()]

    def get_adapter(self, name: str):
        """Return the adapter with the given name, or None."""
        for a in self._adapters:
            if a.name == name:
                return a
        return None
