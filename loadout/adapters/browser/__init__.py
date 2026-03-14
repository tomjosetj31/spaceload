"""Browser adapter package for ctx."""

from loadout.adapters.browser.base import BrowserAdapter, TabSet
from loadout.adapters.browser.registry import BrowserAdapterRegistry

__all__ = ["BrowserAdapter", "TabSet", "BrowserAdapterRegistry"]
