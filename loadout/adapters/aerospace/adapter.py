"""AeroSpace adapter — re-exported from loadout.adapters.wm for backward compatibility.

New code should import from loadout.adapters.wm directly.
"""

from __future__ import annotations

from loadout.adapters.wm.aerospace import AeroSpaceAdapter
from loadout.adapters.wm.base import WMWindow as AeroWindow  # legacy alias

# App name maps kept here for backward compat; canonical home is ctx.adapters.wm.app_names
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

__all__ = [
    "AeroSpaceAdapter",
    "AeroWindow",
    "BROWSER_APP_NAMES",
    "IDE_APP_NAMES",
    "TERMINAL_APP_NAMES",
]
