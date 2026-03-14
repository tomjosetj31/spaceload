"""Maps ctx adapter names to OS-level application names used by tiling WMs."""

from __future__ import annotations

# Maps ctx browser adapter name → app name as reported by the WM
BROWSER_APP_NAMES: dict[str, str] = {
    "chrome": "Google Chrome",
    "safari": "Safari",
    "arc": "Arc",
    "firefox": "Firefox",
}

# Maps ctx IDE adapter name → app name as reported by the WM
IDE_APP_NAMES: dict[str, str] = {
    "vscode": "Code",
    "cursor": "Cursor",
    "zed": "Zed",
}

# Maps ctx terminal adapter name → app name as reported by the WM
TERMINAL_APP_NAMES: dict[str, str] = {
    "iterm2": "iTerm2",
    "terminal": "Terminal",
    "warp": "Warp",
    "kitty": "kitty",
}
