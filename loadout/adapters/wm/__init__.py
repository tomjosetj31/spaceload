"""Workspace manager adapter package for ctx.

Provides a unified interface for tiling window managers (AeroSpace, yabai, …)
so ctx can record and restore window placements regardless of which WM the
user has installed.
"""

from loadout.adapters.wm.base import WMWindow, WorkspaceManagerAdapter
from loadout.adapters.wm.registry import WorkspaceManagerRegistry

__all__ = ["WMWindow", "WorkspaceManagerAdapter", "WorkspaceManagerRegistry"]
