"""IDE adapter base class for ctx."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class ProjectSet:
    """Represents the currently open projects in an IDE."""

    client: str
    paths: list[str] = field(default_factory=list)


class IDEAdapter(ABC):
    """Abstract base class for IDE adapters."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique identifier for this IDE (e.g. 'vscode', 'zed')."""

    @abstractmethod
    def is_available(self) -> bool:
        """Return True if the IDE binary is present on PATH."""

    @abstractmethod
    def get_open_projects(self) -> list[str]:
        """Return the filesystem paths of currently open projects."""

    @abstractmethod
    def open_project(self, path: str) -> bool:
        """Open *path* in this IDE. Return True on success."""
