"""Zed IDE adapter for ctx."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

from loadout.adapters.ide.base import IDEAdapter

# Zed stores recent projects at this path on macOS
_RECENT_PROJECTS_PATH = Path.home() / ".local/share/zed/recent_projects.json"


class ZedAdapter(IDEAdapter):
    """Adapter for the Zed editor on macOS."""

    @property
    def name(self) -> str:
        return "zed"

    def is_available(self) -> bool:
        return shutil.which("zed") is not None

    def get_open_projects(self) -> list[str]:
        if not _RECENT_PROJECTS_PATH.exists():
            return []
        try:
            data = json.loads(_RECENT_PROJECTS_PATH.read_text())
        except Exception:
            return []
        # Zed stores [{"paths": ["/path/to/project"]}, ...]
        paths = []
        for entry in data:
            for p in entry.get("paths", []):
                if Path(p).exists():
                    paths.append(p)
        return paths

    def open_project(self, path: str) -> bool:
        result = subprocess.run(
            ["zed", path],
            capture_output=True,
        )
        return result.returncode == 0
