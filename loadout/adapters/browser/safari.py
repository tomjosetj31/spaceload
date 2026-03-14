"""Safari browser adapter using AppleScript."""

from __future__ import annotations

import subprocess

from loadout.adapters.browser.base import BrowserAdapter

_GET_TABS_SCRIPT = """\
tell application "Safari"
    set tabURLs to {}
    repeat with w in windows
        if visible of w then
            repeat with t in tabs of w
                set end of tabURLs to URL of t
            end repeat
        end if
    end repeat
    set AppleScript's text item delimiters to "\\n"
    return tabURLs as text
end tell
"""


class SafariAdapter(BrowserAdapter):
    """Adapter for Safari on macOS using AppleScript."""

    @property
    def name(self) -> str:
        return "safari"

    def is_available(self) -> bool:
        result = subprocess.run(
            ["pgrep", "-x", "Safari"],
            capture_output=True,
        )
        return result.returncode == 0

    def get_open_tabs(self) -> list[str]:
        result = subprocess.run(
            ["osascript", "-e", _GET_TABS_SCRIPT],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode != 0 or not result.stdout.strip():
            return []
        return [u for u in result.stdout.strip().splitlines() if u.strip()]

    def open_url(self, url: str) -> bool:
        result = subprocess.run(
            ["open", "-a", "Safari", url],
            capture_output=True,
        )
        return result.returncode == 0
