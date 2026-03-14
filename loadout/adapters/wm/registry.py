"""Workspace manager adapter registry — auto-detects the active WM."""

from __future__ import annotations

from loadout.adapters.wm.aerospace import AeroSpaceAdapter
from loadout.adapters.wm.base import WorkspaceManagerAdapter
from loadout.adapters.wm.yabai import YabaiAdapter


class WorkspaceManagerRegistry:
    """Discovers which tiling window manager is available and returns its adapter.

    Adapters are tried in priority order. The first one whose binary is
    present on PATH is returned as the active adapter.
    """

    def __init__(self) -> None:
        self._adapters: list[WorkspaceManagerAdapter] = [
            AeroSpaceAdapter(),
            YabaiAdapter(),
        ]

    def detect_active(self) -> WorkspaceManagerAdapter | None:
        """Return the first available WM adapter, or None if none found."""
        for adapter in self._adapters:
            if adapter.is_available():
                return adapter
        return None

    def get_adapter(self, name: str) -> WorkspaceManagerAdapter | None:
        """Return adapter by name, or None."""
        for adapter in self._adapters:
            if adapter.name == name:
                return adapter
        return None

    def available_adapters(self) -> list[WorkspaceManagerAdapter]:
        """Return all adapters whose binary is present."""
        return [a for a in self._adapters if a.is_available()]
