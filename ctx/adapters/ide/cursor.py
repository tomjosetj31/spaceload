"""Cursor IDE adapter for ctx.

Cursor is based on VS Code, so uses similar detection methods.
"""

from __future__ import annotations

import json
import logging
import re
import shutil
import subprocess
from pathlib import Path
from urllib.parse import unquote

from ctx.adapters.ide.base import IDEAdapter

logger = logging.getLogger(__name__)

_STORAGE_PATH = (
    Path.home() / "Library/Application Support/Cursor/User/globalStorage/storage.json"
)

# AppleScript to get Cursor window titles
_GET_WINDOW_TITLES_SCRIPT = """\
tell application "System Events"
    if exists (process "Cursor") then
        tell process "Cursor"
            set windowNames to {}
            repeat with w in windows
                set end of windowNames to name of w
            end repeat
            set AppleScript's text item delimiters to "\\n"
            return windowNames as text
        end tell
    else
        return ""
    end if
end tell
"""


def _parse_uri(uri: str) -> str | None:
    """Parse a Cursor/VS Code URI and return a displayable path."""
    if not uri:
        return None
    
    if uri.startswith("file://"):
        return unquote(uri[7:])
    
    if uri.startswith("vscode-remote://"):
        remote_part = uri[16:]
        if "/" in remote_part:
            authority, path = remote_part.split("/", 1)
            path = "/" + unquote(path)
        else:
            authority = remote_part
            path = ""
        
        if "+" in authority:
            remote_type, target = authority.split("+", 1)
            target = unquote(target)
            if remote_type == "ssh-remote":
                return f"ssh://{target}{path}"
            elif remote_type == "wsl":
                return f"wsl://{target}{path}"
            else:
                return f"{remote_type}://{target}{path}"
        
        return f"remote://{authority}{path}"
    
    return None


def _get_projects_from_applescript() -> list[str]:
    """Get open project paths from Cursor window titles."""
    try:
        result = subprocess.run(
            ["osascript", "-e", _GET_WINDOW_TITLES_SCRIPT],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode != 0 or not result.stdout.strip():
            return []
        
        projects = []
        for title in result.stdout.strip().split("\n"):
            if not title or "Cursor" not in title:
                continue
            
            # Remove " — Cursor" or " - Cursor" suffix
            title = re.sub(r"\s*[—-]\s*Cursor$", "", title)
            
            # Check for remote prefix
            remote_match = re.match(r"\[([^\]]+)\]\s*(.+)", title)
            if remote_match:
                remote_info = remote_match.group(1)
                rest = remote_match.group(2)
                project_name = rest.split(" — ")[0].split(" - ")[0].strip()
                
                if "SSH:" in remote_info:
                    host = remote_info.replace("SSH:", "").strip()
                    projects.append(f"ssh://{host}/{project_name}")
                else:
                    projects.append(f"remote://{remote_info}/{project_name}")
            else:
                project_name = title.split(" — ")[0].split(" - ")[0].strip()
                if project_name:
                    projects.append(project_name)
        
        logger.debug("CursorAdapter: AppleScript found projects: %s", projects)
        return projects
        
    except Exception as e:
        logger.debug("CursorAdapter: AppleScript error: %s", e)
        return []


def _get_projects_from_storage(storage_path: Path) -> list[str]:
    """Return workspace paths from Cursor's storage.json."""
    try:
        data = json.loads(storage_path.read_text())
    except Exception:
        return []
    
    paths = []
    
    # Read from windowsState
    windows_state = data.get("windowsState", {})
    
    last_window = windows_state.get("lastActiveWindow", {})
    if last_window:
        uri = last_window.get("folder", "") or last_window.get("workspace", "")
        if isinstance(uri, dict):
            uri = uri.get("configPath", "")
        parsed = _parse_uri(uri)
        if parsed:
            paths.append(parsed)
    
    for window in windows_state.get("openedWindows", []):
        uri = window.get("folder", "") or window.get("workspace", "")
        if isinstance(uri, dict):
            uri = uri.get("configPath", "")
        parsed = _parse_uri(uri)
        if parsed and parsed not in paths:
            paths.append(parsed)
    
    # Fallback to legacy format
    if not paths:
        entries = data.get("openedPathsList", {}).get("workspaces3", [])
        for entry in entries:
            uri = entry.get("folderUri", "") or entry.get("fileUri", "")
            parsed = _parse_uri(uri)
            if parsed and parsed not in paths:
                paths.append(parsed)
    
    logger.debug("CursorAdapter: storage found projects: %s", paths)
    return paths


class CursorAdapter(IDEAdapter):
    """Adapter for the Cursor IDE on macOS."""

    @property
    def name(self) -> str:
        return "cursor"

    def is_available(self) -> bool:
        result = subprocess.run(
            ["pgrep", "-x", "Cursor"],
            capture_output=True,
        )
        if result.returncode == 0:
            return True
        return shutil.which("cursor") is not None

    def get_open_projects(self) -> list[str]:
        projects = set()
        
        # Method 1: AppleScript
        projects.update(_get_projects_from_applescript())
        
        # Method 2: Storage file
        if _STORAGE_PATH.exists():
            projects.update(_get_projects_from_storage(_STORAGE_PATH))
        
        result = list(projects)
        logger.info("CursorAdapter: open projects: %s", result)
        return result

    def open_project(self, path: str) -> bool:
        # Handle remote paths
        if path.startswith("ssh://"):
            match = re.match(r"ssh://([^/]+)(/.+)?", path)
            if match:
                host = match.group(1)
                remote_path = match.group(2) or "/"
                result = subprocess.run(
                    ["cursor", "--remote", f"ssh-remote+{host}", remote_path],
                    capture_output=True,
                )
                return result.returncode == 0
        
        result = subprocess.run(
            ["cursor", path],
            capture_output=True,
        )
        return result.returncode == 0
