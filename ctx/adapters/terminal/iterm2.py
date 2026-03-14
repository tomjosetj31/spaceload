"""iTerm2 terminal adapter for ctx."""

from __future__ import annotations

import logging
import subprocess
from dataclasses import dataclass

from ctx.adapters.terminal.base import TerminalAdapter, TerminalSession

logger = logging.getLogger(__name__)


@dataclass
class TTYInfo:
    """Information about a terminal tty."""
    tty: str
    cwd: str | None

# AppleScript to get tty paths from all iTerm2 sessions
_GET_TTYS_SCRIPT = """\
tell application "iTerm2"
    set ttyList to {}
    repeat with w in windows
        repeat with t in tabs of w
            set s to current session of t
            try
                set ttyPath to tty of s
                if ttyPath is not missing value then
                    set end of ttyList to ttyPath
                end if
            end try
        end repeat
    end repeat
    set AppleScript's text item delimiters to "\\n"
    return ttyList as text
end tell
"""


def _get_cwd_from_tty(tty: str) -> str | None:
    """Get the current working directory of the foreground process on a tty.
    
    Uses lsof to find the process and its cwd.
    """
    try:
        # Get the PID of processes using this tty
        pid_result = subprocess.run(
            ["lsof", "-t", tty],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if pid_result.returncode != 0 or not pid_result.stdout.strip():
            return None
        
        # Take the first PID (foreground process)
        pid = pid_result.stdout.strip().split("\n")[0]
        
        # Get the cwd of this process
        cwd_result = subprocess.run(
            ["lsof", "-p", pid],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if cwd_result.returncode != 0:
            return None
        
        # Parse lsof output to find cwd
        for line in cwd_result.stdout.split("\n"):
            if "cwd" in line:
                parts = line.split()
                if parts:
                    return parts[-1]
        return None
    except (subprocess.SubprocessError, OSError, IndexError) as e:
        logger.debug("iTerm2Adapter: failed to get cwd from tty %s: %s", tty, e)
        return None


class ITerm2Adapter(TerminalAdapter):
    """Adapter for iTerm2 on macOS."""

    @property
    def name(self) -> str:
        return "iterm2"

    def is_available(self) -> bool:
        # Try multiple process name patterns as iTerm2 process name varies
        for pattern in ["iTerm2", "iTerm"]:
            result = subprocess.run(
                ["pgrep", "-x", pattern],
                capture_output=True,
            )
            if result.returncode == 0:
                logger.debug("iTerm2Adapter: is_available=True (matched %s)", pattern)
                return True
        
        # Fallback: check if the AppleScript can communicate with iTerm2
        result = subprocess.run(
            ["osascript", "-e", 'tell application "System Events" to (name of processes) contains "iTerm2"'],
            capture_output=True,
            text=True,
            timeout=5,
        )
        available = result.returncode == 0 and "true" in result.stdout.lower()
        logger.debug("iTerm2Adapter: is_available=%s (via System Events)", available)
        return available

    def _get_tty_info_list(self) -> list[TTYInfo]:
        """Get all tty paths and their working directories.
        
        Returns a list of TTYInfo objects, one per terminal session.
        """
        try:
            # Get tty paths from iTerm2
            result = subprocess.run(
                ["osascript", "-e", _GET_TTYS_SCRIPT],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode != 0:
                logger.warning(
                    "iTerm2Adapter: AppleScript failed: %s", 
                    result.stderr.strip()
                )
                return []
            
            output = result.stdout.strip()
            if not output:
                logger.debug("iTerm2Adapter: no tty paths returned")
                return []
            
            ttys = [t for t in output.split("\n") if t]
            logger.debug("iTerm2Adapter: found ttys: %s", ttys)
            
            # Get cwd for each tty
            tty_info_list = []
            for tty in ttys:
                cwd = _get_cwd_from_tty(tty)
                tty_info_list.append(TTYInfo(tty=tty, cwd=cwd))
                if cwd:
                    logger.debug("iTerm2Adapter: tty %s -> cwd %s", tty, cwd)
            
            return tty_info_list
            
        except subprocess.TimeoutExpired:
            logger.warning("iTerm2Adapter: timeout getting tty info")
            return []
        except Exception as e:
            logger.warning("iTerm2Adapter: error getting tty info: %s", e)
            return []

    def get_open_dirs(self) -> list[str]:
        """Get working directories of all open iTerm2 sessions.
        
        Uses AppleScript to get tty paths, then lsof to find the cwd
        of the foreground process on each tty.
        """
        tty_info_list = self._get_tty_info_list()
        
        # Remove duplicates while preserving order
        seen = set()
        unique_dirs = []
        for info in tty_info_list:
            if info.cwd and info.cwd not in seen:
                seen.add(info.cwd)
                unique_dirs.append(info.cwd)
        
        logger.info("iTerm2Adapter: open directories: %s", unique_dirs)
        return unique_dirs

    def get_sessions(self) -> list[TerminalSession]:
        """Get all open iTerm2 sessions with their tty identifiers.
        
        This returns one session per terminal tab/window, allowing
        tracking of multiple terminals even if they're in the same directory.
        """
        tty_info_list = self._get_tty_info_list()
        
        sessions = []
        for info in tty_info_list:
            if info.cwd:
                sessions.append(TerminalSession(
                    app=self.name,
                    directory=info.cwd,
                    session_id=info.tty,  # Use tty as unique identifier
                ))
        
        logger.info("iTerm2Adapter: found %d sessions", len(sessions))
        return sessions

    def open_in_dir(self, directory: str) -> bool:
        """Open a new iTerm2 tab/window in the specified directory.
        
        Creates a new tab in the current window (or a new window if none exists).
        Uses 'cd' with clear to start with a clean prompt in the target directory.
        """
        return self.open_with_commands(directory, [])

    def open_with_commands(self, start_directory: str, commands: list[str]) -> bool:
        """Open a new iTerm2 tab and run a sequence of commands.
        
        Args:
            start_directory: Initial directory to cd into
            commands: List of commands to run in sequence
        
        Creates a new tab, cds to start_directory, then runs each command.
        """
        def escape_for_applescript(s: str) -> str:
            """Escape a string for use inside AppleScript double quotes."""
            # Escape backslashes first, then double quotes
            return s.replace("\\", "\\\\").replace('"', '\\"')
        
        # Escape directory for shell (single quotes)
        escaped_dir = start_directory.replace("'", "'\\''")
        
        # Build the command sequence
        # Start with cd to initial directory
        all_commands = [f"cd '{escaped_dir}'"]
        
        # Add user commands as-is (they'll be escaped for AppleScript below)
        all_commands.extend(commands)
        
        # Build AppleScript with write text for each command
        # Each command needs to be escaped for AppleScript string syntax
        write_statements = "\n        ".join(
            f'write text "{escape_for_applescript(cmd)}"' for cmd in all_commands
        )
        
        script = f'''
tell application "iTerm2"
    activate
    
    -- Try to create a tab in the current window, fall back to new window
    if (count of windows) > 0 then
        tell current window
            create tab with default profile
        end tell
    else
        create window with default profile
    end if
    
    -- Run commands in sequence
    tell current session of current window
        {write_statements}
    end tell
end tell
'''
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
        )
        success = result.returncode == 0
        if success:
            logger.info("iTerm2Adapter: opened tab in %s with %d commands", start_directory, len(commands))
        else:
            logger.warning("iTerm2Adapter: failed to open tab: %s", result.stderr.decode())
        return success
