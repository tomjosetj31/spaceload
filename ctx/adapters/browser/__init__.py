"""Browser adapter package for ctx."""

from ctx.adapters.browser.base import BrowserAdapter, TabSet
from ctx.adapters.browser.registry import BrowserAdapterRegistry

__all__ = ["BrowserAdapter", "TabSet", "BrowserAdapterRegistry"]
