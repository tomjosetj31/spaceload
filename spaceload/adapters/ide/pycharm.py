"""PyCharm IDE adapter for spaceload."""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path

from spaceload.adapters.ide.base import IDEAdapter

logger = logging.getLogger(__name__)

# Known PyCharm application bundle names (CE and Professional)
_APP_NAMES = ["PyCharm", "PyCharm CE"]

# AppleScript to get window titles from any running PyCharm variant
_GET_WINDOW_TITLES_SCRIPT_TMPL = """\
tell application "System Events"
    if exists (process "{app}") then
        tell process "{app}"
            set windowNames to {{}}
            repeat with w in windows
                set end of windowNames to name of w
            end repeat
            set AppleScript's text item delimiters to "\\n"
            return windowNames as text
        end tell
    end if
    return ""
end tell
"""


def _pycharm_process_names() -> list[str]:
    """Return the OS-level process names of running PyCharm variants."""
    running = []
    for app in _APP_NAMES:
        result = subprocess.run(
            ["pgrep", "-x", app],
            capture_output=True,
        )
        if result.returncode == 0:
            running.append(app)
    return running


def _get_open_projects_from_applescript(app_name: str) -> list[str]:
    """Read open project paths from PyCharm window titles via AppleScript.

    PyCharm window titles look like:
    - "project-name – main.py"
    - "project-name [~/projects/project-name]"
    - "~/projects/project-name – main.py"
    """
    try:
        script = _GET_WINDOW_TITLES_SCRIPT_TMPL.format(app=app_name)
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode != 0 or not result.stdout.strip():
            return []
        paths = []
        for title in result.stdout.strip().split("\n"):
            if not title:
                continue
            # Extract bracketed path: "name [/full/path]"
            if "[" in title and "]" in title:
                bracket_start = title.rfind("[")
                bracket_end = title.rfind("]")
                candidate = title[bracket_start + 1 : bracket_end].strip()
                expanded = str(Path(candidate).expanduser())
                if Path(expanded).exists():
                    paths.append(expanded)
                    continue
            # Strip " – ..." or " — ..." filename suffix and try as a path
            for sep in (" – ", " — ", " - "):
                if sep in title:
                    candidate = title.split(sep)[0].strip()
                    break
            else:
                candidate = title.strip()
            expanded = str(Path(candidate).expanduser())
            if Path(expanded).is_dir():
                paths.append(expanded)
        return paths
    except (subprocess.SubprocessError, OSError) as exc:
        logger.debug("PyCharmAdapter: AppleScript error: %s", exc)
        return []


class PyCharmAdapter(IDEAdapter):
    """Adapter for PyCharm (Community Edition and Professional) on macOS."""

    @property
    def name(self) -> str:
        return "pycharm"

    def is_available(self) -> bool:
        """Return True if any PyCharm variant is running."""
        return bool(_pycharm_process_names())

    def get_open_projects(self) -> list[str]:
        """Return the filesystem paths of all currently open PyCharm projects."""
        paths: set[str] = set()
        for app_name in _pycharm_process_names():
            paths.update(_get_open_projects_from_applescript(app_name))
        result = list(paths)
        logger.info("PyCharmAdapter: open projects: %s", result)
        return result

    def open_project(self, path: str) -> bool:
        """Open a project in PyCharm using 'open -a PyCharm /path'."""
        # Try Professional first, then CE
        for app in _APP_NAMES:
            result = subprocess.run(
                ["open", "-a", app, path],
                capture_output=True,
            )
            if result.returncode == 0:
                return True
        logger.warning("PyCharmAdapter.open_project(): could not open %r", path)
        return False
