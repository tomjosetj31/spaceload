"""AeroSpace tiling window manager adapter."""

from __future__ import annotations

import shutil
import subprocess

from loadout.adapters.wm.base import WMWindow, WorkspaceManagerAdapter


class AeroSpaceAdapter(WorkspaceManagerAdapter):
    """Adapter for AeroSpace (https://github.com/nikitabobko/AeroSpace).

    Uses the `aerospace` CLI to list windows and move them between
    named workspaces (e.g. '1', '2', 'Q', 'C', …).
    """

    @property
    def name(self) -> str:
        return "aerospace"

    def is_available(self) -> bool:
        return shutil.which("aerospace") is not None

    def list_windows(self) -> list[WMWindow]:
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

        windows: list[WMWindow] = []
        for line in result.stdout.strip().splitlines():
            parts = line.split(" ", 2)
            if len(parts) < 3:
                continue
            try:
                windows.append(
                    WMWindow(
                        window_id=int(parts[0]),
                        workspace=parts[1],
                        app_name=parts[2].strip(),
                    )
                )
            except ValueError:
                continue
        return windows

    def move_window_to_workspace(self, window_id: int, workspace: str) -> bool:
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
