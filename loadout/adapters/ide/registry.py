"""IDE adapter registry for ctx."""

from __future__ import annotations

from loadout.adapters.ide.base import IDEAdapter
from loadout.adapters.ide.cursor import CursorAdapter
from loadout.adapters.ide.vscode import VSCodeAdapter
from loadout.adapters.ide.zed import ZedAdapter


class IDEAdapterRegistry:
    """Discovers and exposes available IDE adapters."""

    def __init__(self) -> None:
        self._adapters: list[IDEAdapter] = [
            VSCodeAdapter(),
            CursorAdapter(),
            ZedAdapter(),
        ]

    def available_adapters(self) -> list[IDEAdapter]:
        """Return adapters whose IDE binary is present on PATH."""
        return [a for a in self._adapters if a.is_available()]

    def get_adapter(self, name: str) -> IDEAdapter | None:
        """Return adapter by name, or None if not found."""
        for adapter in self._adapters:
            if adapter.name == name:
                return adapter
        return None
