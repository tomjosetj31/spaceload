"""yabai tiling window manager adapter."""

from __future__ import annotations

import json
import shutil
import subprocess

from loadout.adapters.wm.base import WMWindow, WorkspaceManagerAdapter


class YabaiAdapter(WorkspaceManagerAdapter):
    """Adapter for yabai (https://github.com/koekeishiya/yabai).

    Uses `yabai -m query --windows` (JSON) to list windows and
    `yabai -m window <id> --space <space>` to move them.

    Yabai uses integer space indexes; ctx stores them as strings for
    uniformity with other WM adapters.
    """

    @property
    def name(self) -> str:
        return "yabai"

    def is_available(self) -> bool:
        return shutil.which("yabai") is not None

    def list_windows(self) -> list[WMWindow]:
        result = subprocess.run(
            ["yabai", "-m", "query", "--windows"],
            capture_output=True,
            text=True,
            timeout=3,
        )
        if result.returncode != 0 or not result.stdout.strip():
            return []

        try:
            raw = json.loads(result.stdout)
        except json.JSONDecodeError:
            return []

        windows: list[WMWindow] = []
        for w in raw:
            try:
                windows.append(
                    WMWindow(
                        window_id=int(w["id"]),
                        workspace=str(w.get("space", "")),
                        app_name=w.get("app", ""),
                    )
                )
            except (KeyError, ValueError):
                continue
        return windows

    def move_window_to_workspace(self, window_id: int, workspace: str) -> bool:
        result = subprocess.run(
            ["yabai", "-m", "window", str(window_id), "--space", workspace],
            capture_output=True,
        )
        return result.returncode == 0
