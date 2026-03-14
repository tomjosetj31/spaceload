"""Terminal.app adapter for ctx."""

from __future__ import annotations

import subprocess

from loadout.adapters.terminal.base import TerminalAdapter

_GET_TTYS_SCRIPT = """\
tell application "Terminal"
    set ttyList to {}
    repeat with aWindow in windows
        repeat with aTab in tabs of aWindow
            set end of ttyList to tty of aTab
        end repeat
    end repeat
    set AppleScript's text item delimiters to "\\n"
    return ttyList as text
end tell
"""


class TerminalAppAdapter(TerminalAdapter):
    """Adapter for macOS Terminal.app."""

    @property
    def name(self) -> str:
        return "terminal"

    def is_available(self) -> bool:
        result = subprocess.run(
            ["pgrep", "-x", "Terminal"],
            capture_output=True,
        )
        return result.returncode == 0

    def get_open_dirs(self) -> list[str]:
        try:
            result = subprocess.run(
                ["osascript", "-e", _GET_TTYS_SCRIPT],
                capture_output=True,
                text=True,
            )
            if result.returncode != 0:
                return []
            output = result.stdout.strip()
            if not output:
                return []
            ttys = [t for t in output.split("\n") if t]
            dirs: list[str] = []
            for tty in ttys:
                cwd = self._cwd_for_tty(tty)
                if cwd:
                    dirs.append(cwd)
            return dirs
        except Exception:
            return []

    def _cwd_for_tty(self, tty: str) -> str | None:
        """Return the cwd of the shell process on *tty*, or None."""
        try:
            pid_result = subprocess.run(
                ["lsof", "-t", tty],
                capture_output=True,
                text=True,
            )
            if pid_result.returncode != 0 or not pid_result.stdout.strip():
                return None
            pids = pid_result.stdout.strip().split("\n")
            for pid in pids:
                pid = pid.strip()
                if not pid:
                    continue
                cwd_result = subprocess.run(
                    ["lsof", "-p", pid, "-a", "-d", "cwd", "-Fn"],
                    capture_output=True,
                    text=True,
                )
                for line in cwd_result.stdout.splitlines():
                    if line.startswith("n"):
                        return line[1:]
            return None
        except Exception:
            return None

    def open_in_dir(self, directory: str) -> bool:
        script = f"tell application \"Terminal\" to do script \"cd '{directory}'\""
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
        )
        return result.returncode == 0
