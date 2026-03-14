"""Browser adapter registry for ctx."""

from __future__ import annotations

from ctx.adapters.browser.arc import ArcAdapter
from ctx.adapters.browser.base import BrowserAdapter
from ctx.adapters.browser.chrome import ChromeAdapter
from ctx.adapters.browser.safari import SafariAdapter


class BrowserAdapterRegistry:
    """Discovers and exposes available browser adapters."""

    def __init__(self) -> None:
        self._adapters: list[BrowserAdapter] = [
            ChromeAdapter(),
            ArcAdapter(),
            SafariAdapter(),
        ]

    def available_adapters(self) -> list[BrowserAdapter]:
        """Return adapters whose browser is currently running."""
        return [a for a in self._adapters if a.is_available()]

    def get_adapter(self, name: str) -> BrowserAdapter | None:
        """Return adapter by name, or None if not found."""
        for adapter in self._adapters:
            if adapter.name == name:
                return adapter
        return None
