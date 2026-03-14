"""AeroSpace window manager adapter for ctx.

Wraps the `aerospace` CLI to query which workspace each app window lives in
and to move windows between workspaces on replay.
"""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass


@dataclass
class AeroWindow:
    """A single window as reported by `aerospace list-windows`."""

    window_id: int
    workspace: str
    app_name: str


# Maps ctx adapter names → AeroSpace app-name strings
BROWSER_APP_NAMES: dict[str, str] = {
    "chrome": "Google Chrome",
    "safari": "Safari",
    "arc": "Arc",
    "firefox": "Firefox",
}

IDE_APP_NAMES: dict[str, str] = {
    "vscode": "Code",
    "cursor": "Cursor",
    "zed": "Zed",
}

TERMINAL_APP_NAMES: dict[str, str] = {
    "iterm2": "iTerm2",
    "terminal": "Terminal",
    "warp": "Warp",
    "kitty": "kitty",
}


class AeroSpaceAdapter:
    """Thin wrapper around the `aerospace` CLI."""

    def is_available(self) -> bool:
        """Return True if the aerospace binary is on PATH."""
        return shutil.which("aerospace") is not None

    def list_windows(self) -> list[AeroWindow]:
        """Return all open windows with their workspace assignments."""
        result = subprocess.run(
            [
                "aerospace",
                "list-windows",
                "--all",
                "--format",
                "%{window-id} %{workspace} %{app-name}",
            ],
            capture_output=True,
            text=True,
            timeout=3,
        )
        if result.returncode != 0 or not result.stdout.strip():
            return []

        windows: list[AeroWindow] = []
        for line in result.stdout.strip().splitlines():
            parts = line.split(" ", 2)
            if len(parts) < 3:
                continue
            try:
                windows.append(
                    AeroWindow(
                        window_id=int(parts[0]),
                        workspace=parts[1],
                        app_name=parts[2].strip(),
                    )
                )
            except ValueError:
                continue
        return windows

    def get_app_workspace(self, app_name: str) -> str | None:
        """Return the workspace ID for the first window of *app_name*, or None."""
        for w in self.list_windows():
            if w.app_name == app_name:
                return w.workspace
        return None

    def get_app_window_ids(self, app_name: str) -> list[int]:
        """Return all window IDs belonging to *app_name*."""
        return [w.window_id for w in self.list_windows() if w.app_name == app_name]

    def move_window_to_workspace(self, window_id: int, workspace: str) -> bool:
        """Move a specific window to *workspace*. Return True on success."""
        result = subprocess.run(
            [
                "aerospace",
                "move-node-to-workspace",
                "--window-id",
                str(window_id),
                workspace,
            ],
            capture_output=True,
        )
        return result.returncode == 0

    def move_app_to_workspace(self, app_name: str, workspace: str) -> bool:
        """Move the first window of *app_name* to *workspace*."""
        ids = self.get_app_window_ids(app_name)
        if not ids:
            return False
        return self.move_window_to_workspace(ids[0], workspace)
