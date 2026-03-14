"""Browser adapter base class for ctx."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class TabSet:
    """Represents the current open tabs in a browser."""

    browser: str
    urls: list[str] = field(default_factory=list)


class BrowserAdapter(ABC):
    """Abstract base class for browser adapters."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique identifier for this browser (e.g. 'chrome', 'safari')."""

    @abstractmethod
    def is_available(self) -> bool:
        """Return True if this browser is currently running."""

    @abstractmethod
    def get_open_tabs(self) -> list[str]:
        """Return the URLs of all currently open tabs."""

    @abstractmethod
    def open_url(self, url: str) -> bool:
        """Open *url* in this browser. Return True on success."""
