"""Abstract base class for tiling window manager adapters."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class WMWindow:
    """A single window as reported by a tiling window manager."""

    window_id: int
    workspace: str   # workspace/space identifier (string for uniformity)
    app_name: str


class WorkspaceManagerAdapter(ABC):
    """Abstract interface for tiling window manager integrations.

    Implementations wrap the CLI of a specific WM (AeroSpace, yabai, …)
    and expose a uniform API for querying window locations and moving
    windows between workspaces/spaces.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique lowercase identifier (e.g. 'aerospace', 'yabai')."""

    @abstractmethod
    def is_available(self) -> bool:
        """Return True if this WM's binary is on PATH and the WM is running."""

    @abstractmethod
    def list_windows(self) -> list[WMWindow]:
        """Return all managed windows with their current workspace assignment."""

    def get_app_workspace(self, app_name: str) -> str | None:
        """Return the workspace of the first window belonging to *app_name*."""
        for w in self.list_windows():
            if w.app_name == app_name:
                return w.workspace
        return None

    def get_app_window_ids(self, app_name: str) -> list[int]:
        """Return all window IDs belonging to *app_name*."""
        return [w.window_id for w in self.list_windows() if w.app_name == app_name]

    @abstractmethod
    def move_window_to_workspace(self, window_id: int, workspace: str) -> bool:
        """Move *window_id* to *workspace*. Return True on success."""

    def move_app_to_workspace(self, app_name: str, workspace: str) -> bool:
        """Move the first window of *app_name* to *workspace*."""
        ids = self.get_app_window_ids(app_name)
        if not ids:
            return False
        return self.move_window_to_workspace(ids[0], workspace)
