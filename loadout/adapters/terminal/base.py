"""Terminal adapter base class for ctx."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class TerminalSession:
    """Represents an open terminal session."""

    app: str
    directory: str
    session_id: str = ""  # Unique identifier (e.g., tty path) for the session


class TerminalAdapter(ABC):
    """Abstract base class for terminal adapters."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique identifier (e.g. 'iterm2', 'terminal')."""

    @abstractmethod
    def is_available(self) -> bool:
        """Return True if this terminal app is currently running."""

    @abstractmethod
    def get_open_dirs(self) -> list[str]:
        """Return working directories of all currently open terminal sessions."""

    def get_sessions(self) -> list[TerminalSession]:
        """Return all open terminal sessions with their identifiers.
        
        Default implementation converts get_open_dirs() to sessions.
        Adapters should override this for better session tracking.
        """
        return [
            TerminalSession(app=self.name, directory=d, session_id=f"{self.name}:{d}")
            for d in self.get_open_dirs()
        ]

    @abstractmethod
    def open_in_dir(self, directory: str) -> bool:
        """Open a new terminal session in directory. Return True on success."""
