"""Visual Studio Code IDE adapter for ctx.

Supports multiple methods for detecting open projects:
1. AppleScript - gets window titles from running VS Code (most reliable)
2. Storage file - reads windowsState from storage.json
3. Supports both local and remote (SSH, WSL, containers) workspaces
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

# VS Code stores state in these locations on macOS
_STORAGE_CANDIDATES = [
    Path.home() / "Library/Application Support/Code/User/globalStorage/storage.json",
    Path.home() / "Library/Application Support/VSCodium/User/globalStorage/storage.json",
]

# AppleScript to get VS Code window titles
_GET_WINDOW_TITLES_SCRIPT = """\
tell application "System Events"
    if exists (process "Code") then
        tell process "Code"
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
    """Parse a VS Code URI and return a displayable path.
    
    Handles:
    - file:///path/to/folder -> /path/to/folder
    - vscode-remote://ssh-remote+host/path -> ssh://host/path
    - vscode-remote://wsl+distro/path -> wsl://distro/path
    - vscode-remote://dev-container+id/path -> container://id/path
    """
    if not uri:
        return None
    
    # Local file
    if uri.startswith("file://"):
        path = unquote(uri[7:])  # Remove "file://" and decode URL encoding
        return path
    
    # Remote workspace (SSH, WSL, containers, etc.)
    if uri.startswith("vscode-remote://"):
        # Format: vscode-remote://type+target/path
        remote_part = uri[16:]  # Remove "vscode-remote://"
        
        # Parse the remote authority and path
        if "/" in remote_part:
            authority, path = remote_part.split("/", 1)
            path = "/" + unquote(path)
        else:
            authority = remote_part
            path = ""
        
        # Decode the authority (e.g., "ssh-remote+devvm" -> type="ssh-remote", target="devvm")
        if "+" in authority:
            remote_type, target = authority.split("+", 1)
            target = unquote(target)
            
            # Create a readable representation
            if remote_type == "ssh-remote":
                return f"ssh://{target}{path}"
            elif remote_type == "wsl":
                return f"wsl://{target}{path}"
            elif remote_type == "dev-container":
                return f"container://{target}{path}"
            elif remote_type == "codespaces":
                return f"codespace://{target}{path}"
            else:
                return f"{remote_type}://{target}{path}"
        
        return f"remote://{authority}{path}"
    
    return None


def _get_projects_from_applescript() -> list[str]:
    """Get open project paths from VS Code window titles using AppleScript.
    
    Window titles typically look like:
    - "ProjectName — filename.py — Visual Studio Code"
    - "folder — Visual Studio Code"
    - "[SSH: hostname] folder — Visual Studio Code"
    - "filename.py — Visual Studio Code" (single file, no folder)
    """
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
            if not title or "Visual Studio Code" not in title:
                continue
            
            # Parse window title
            # Format: "[Remote] ProjectName — file.py — Visual Studio Code"
            # or: "ProjectName — Visual Studio Code"
            
            # Remove " — Visual Studio Code" suffix
            title = re.sub(r"\s*—\s*Visual Studio Code$", "", title)
            
            # Check for remote prefix like "[SSH: hostname]"
            remote_match = re.match(r"\[([^\]]+)\]\s*(.+)", title)
            if remote_match:
                remote_info = remote_match.group(1)
                rest = remote_match.group(2)
                # Extract project name (first part before " — ")
                project_name = rest.split(" — ")[0].strip()
                
                # Create a remote path identifier
                if "SSH:" in remote_info:
                    host = remote_info.replace("SSH:", "").strip()
                    projects.append(f"ssh://{host}/{project_name}")
                elif "WSL:" in remote_info:
                    distro = remote_info.replace("WSL:", "").strip()
                    projects.append(f"wsl://{distro}/{project_name}")
                elif "Container" in remote_info or "Dev Container" in remote_info:
                    projects.append(f"container://{project_name}")
                else:
                    projects.append(f"remote://{remote_info}/{project_name}")
            else:
                # Local project - first part is project/folder name
                project_name = title.split(" — ")[0].strip()
                if project_name:
                    # Try to find the full path by matching against common locations
                    full_path = _find_project_path(project_name)
                    if full_path:
                        projects.append(full_path)
                    else:
                        projects.append(project_name)
        
        logger.debug("VSCodeAdapter: AppleScript found projects: %s", projects)
        return projects
        
    except subprocess.TimeoutExpired:
        logger.warning("VSCodeAdapter: AppleScript timeout")
        return []
    except Exception as e:
        logger.warning("VSCodeAdapter: AppleScript error: %s", e)
        return []


def _find_project_path(project_name: str) -> str | None:
    """Try to find the full path for a project name.
    
    Searches common locations like home directory, common project folders.
    """
    search_paths = [
        Path.home(),
        Path.home() / "Projects",
        Path.home() / "projects", 
        Path.home() / "Developer",
        Path.home() / "dev",
        Path.home() / "Code",
        Path.home() / "code",
        Path.home() / "workspace",
        Path.home() / "Workspace",
        Path.home() / "personal",
        Path.home() / "work",
    ]
    
    for base in search_paths:
        candidate = base / project_name
        if candidate.exists() and candidate.is_dir():
            return str(candidate)
    
    # Also check if project_name itself is an absolute path
    if Path(project_name).is_absolute() and Path(project_name).exists():
        return project_name
    
    return None


def _get_projects_from_storage(storage_path: Path) -> list[str]:
    """Return workspace paths from VS Code's storage.json.
    
    Reads from windowsState which contains currently open windows,
    supporting both local and remote workspaces.
    """
    try:
        data = json.loads(storage_path.read_text())
    except Exception as e:
        logger.debug("VSCodeAdapter: failed to read storage.json: %s", e)
        return []
    
    paths = []
    
    # Method 1: Read from windowsState (current windows)
    windows_state = data.get("windowsState", {})
    
    # Last active window
    last_window = windows_state.get("lastActiveWindow", {})
    if last_window:
        folder_uri = last_window.get("folder", "")
        workspace_uri = last_window.get("workspace", {})
        if isinstance(workspace_uri, dict):
            workspace_uri = workspace_uri.get("configPath", "")
        
        uri = folder_uri or workspace_uri
        if uri:
            parsed = _parse_uri(uri)
            if parsed:
                paths.append(parsed)
    
    # Other open windows
    for window in windows_state.get("openedWindows", []):
        folder_uri = window.get("folder", "")
        workspace_uri = window.get("workspace", {})
        if isinstance(workspace_uri, dict):
            workspace_uri = workspace_uri.get("configPath", "")
        
        uri = folder_uri or workspace_uri
        if uri:
            parsed = _parse_uri(uri)
            if parsed and parsed not in paths:
                paths.append(parsed)
    
    # Method 2: Fallback to openedPathsList (legacy format)
    if not paths:
        entries = data.get("openedPathsList", {}).get("workspaces3", [])
        for entry in entries:
            uri = entry.get("folderUri", "") or entry.get("fileUri", "")
            parsed = _parse_uri(uri)
            if parsed and parsed not in paths:
                paths.append(parsed)
    
    logger.debug("VSCodeAdapter: storage.json found projects: %s", paths)
    return paths


class VSCodeAdapter(IDEAdapter):
    """Adapter for Visual Studio Code on macOS.
    
    Uses multiple methods to detect open projects:
    1. AppleScript to get window titles (most reliable for current state)
    2. storage.json for detailed path information
    
    Supports both local and remote workspaces (SSH, WSL, containers).
    """

    @property
    def name(self) -> str:
        return "vscode"

    def is_available(self) -> bool:
        # Check if VS Code is running
        result = subprocess.run(
            ["pgrep", "-x", "Code"],
            capture_output=True,
        )
        if result.returncode == 0:
            return True
        
        # Fallback: check if code CLI exists
        return shutil.which("code") is not None

    def get_open_projects(self) -> list[str]:
        """Get currently open projects from VS Code.
        
        Combines results from AppleScript and storage.json for best coverage.
        """
        projects = set()
        
        # Method 1: AppleScript (gets current window titles)
        applescript_projects = _get_projects_from_applescript()
        projects.update(applescript_projects)
        
        # Method 2: Storage file (gets detailed paths including remote)
        for storage in _STORAGE_CANDIDATES:
            if storage.exists():
                storage_projects = _get_projects_from_storage(storage)
                projects.update(storage_projects)
                break
        
        result = list(projects)
        logger.info("VSCodeAdapter: open projects: %s", result)
        return result

    def open_project(self, path: str) -> bool:
        """Open a project in VS Code.
        
        Handles both local paths and remote URIs.
        """
        # Handle remote paths
        if path.startswith("ssh://"):
            # Convert ssh://host/path to VS Code remote format
            # code --remote ssh-remote+host /path
            match = re.match(r"ssh://([^/]+)(/.+)?", path)
            if match:
                host = match.group(1)
                remote_path = match.group(2) or "/"
                result = subprocess.run(
                    ["code", "--remote", f"ssh-remote+{host}", remote_path],
                    capture_output=True,
                )
                return result.returncode == 0
        
        elif path.startswith("wsl://"):
            match = re.match(r"wsl://([^/]+)(/.+)?", path)
            if match:
                distro = match.group(1)
                remote_path = match.group(2) or "/"
                result = subprocess.run(
                    ["code", "--remote", f"wsl+{distro}", remote_path],
                    capture_output=True,
                )
                return result.returncode == 0
        
        elif path.startswith("container://"):
            # For containers, just try to open - VS Code should handle it
            logger.warning("VSCodeAdapter: container paths may require manual reconnection")
            return False
        
        elif path.startswith("remote://") or path.startswith("codespace://"):
            logger.warning("VSCodeAdapter: remote path %s may require manual setup", path)
            return False
        
        # Local path
        result = subprocess.run(
            ["code", path],
            capture_output=True,
        )
        return result.returncode == 0
