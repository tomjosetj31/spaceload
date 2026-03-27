"""ANSI terminal renderer for the live recording panel.

Uses only raw ANSI escape codes — no external dependencies required.
Gracefully degrades to a no-op when stdout is not a TTY (CI, pipes).

Panel anatomy (W = total width, C = W - 6 = usable content chars):

    ╭─ spaceload recording ─────────────────────────────────╮  <- W chars
    │  {content}{padding}  │                                   <- W chars
    ╰───────────────────────────────────────────────────────╯  <- W chars

The renderer tracks how many lines it printed last cycle and moves the
cursor back up to overwrite them on the next call to render().
"""

from __future__ import annotations

import re
import shutil
import sys
from datetime import datetime, timezone
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from spaceload.tui.recording_view import RecordingView

# ---------------------------------------------------------------------------
# ANSI color codes
# ---------------------------------------------------------------------------

_RESET = "\033[0m"
_GREEN = "\033[32m"
_BRIGHT_GREEN = "\033[92m"
_DIM = "\033[2m"
_BOLD = "\033[1m"
_CYAN = "\033[36m"

# Strip ANSI codes to compute visual (on-screen) length
_ANSI_RE = re.compile(r"\033\[[0-9;]*m")


def _vlen(s: str) -> int:
    """Visual length of *s* after stripping ANSI escape codes."""
    return len(_ANSI_RE.sub("", s))


# ---------------------------------------------------------------------------
# Box-drawing characters
# ---------------------------------------------------------------------------

_TL = "╭"
_TR = "╮"
_BL = "╰"
_BR = "╯"
_H = "─"
_V = "│"
_ML = "├"
_MR = "┤"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def is_tty() -> bool:
    """Return True when stdout is an interactive terminal."""
    return hasattr(sys.stdout, "isatty") and sys.stdout.isatty()


def _panel_width() -> int:
    """Total panel width in characters (including the two border chars)."""
    cols = shutil.get_terminal_size((80, 24)).columns
    return min(max(cols, 62), 102)


def _rel_time(ts: datetime) -> str:
    """Human-readable relative timestamp (e.g. 'just now', '1:23 ago')."""
    secs = int((datetime.now(timezone.utc) - ts).total_seconds())
    if secs < 5:
        return "just now"
    if secs < 60:
        return f"{secs}s ago"
    m, s = divmod(secs, 60)
    if m < 60:
        return f"{m}:{s:02d} ago"
    return "long ago"


def _trunc(text: str, n: int) -> str:
    """Truncate *text* to *n* chars, appending '…' when cut."""
    if len(text) <= n:
        return text
    return text[: n - 1] + "…"


# ---------------------------------------------------------------------------
# Renderer
# ---------------------------------------------------------------------------


class Renderer:
    """Renders the live recording panel to an ANSI terminal.

    Call render(view) in a loop; call clear() before printing anything
    else (e.g. the final summary).
    """

    def __init__(self) -> None:
        self._last_lines: int = 0

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def render(self, view: "RecordingView") -> None:
        """Redraw the live panel in place.

        First call: prints the panel fresh.
        Subsequent calls: moves cursor up and overwrites the previous frame.
        Falls back to a no-op when stdout is not a TTY.
        """
        if not is_tty():
            return

        lines = self._build(view)

        if self._last_lines > 0:
            # Move cursor back to the top of the previous frame
            sys.stdout.write(f"\033[{self._last_lines}A")

        for line in lines:
            # \033[K clears from cursor to end of line (handles shrinking panels)
            sys.stdout.write(line + "\033[K\n")

        sys.stdout.flush()
        self._last_lines = len(lines)

    def clear(self) -> None:
        """Erase the last rendered panel from the terminal."""
        if not is_tty() or self._last_lines == 0:
            return
        sys.stdout.write(f"\033[{self._last_lines}A\033[J")
        sys.stdout.flush()
        self._last_lines = 0

    # ------------------------------------------------------------------
    # Panel layout
    # ------------------------------------------------------------------

    def _row(self, colored: str, W: int) -> str:
        """Build a single panel row with correct border and padding.

        colored  — content string (may contain ANSI codes)
        W        — total panel width (including the two │ chars)
        """
        C = W - 6  # usable content: W - 2 borders - 2 left pad - 2 right pad
        pad = max(0, C - _vlen(colored))
        return f"{_V}  {colored}{' ' * pad}  {_V}"

    def _blank(self, W: int) -> str:
        """An empty panel row (used as section separator)."""
        return f"{_V}{' ' * (W - 2)}{_V}"

    def _build(self, view: "RecordingView") -> list[str]:
        """Build and return the full list of terminal lines for one frame."""
        W = _panel_width()
        H = W - 2   # fill width for horizontal borders (between corner chars)
        C = W - 6   # usable content width

        lines: list[str] = []

        # ── Top border ────────────────────────────────────────────────
        title_v = " spaceload recording "
        title_c = f"{_BOLD}{_CYAN}{title_v}{_RESET}"
        right_dashes = _H * (H - len(title_v) - 1)
        lines.append(f"{_TL}{_H}{title_c}{right_dashes}{_TR}")

        # ── Workspace + elapsed time ───────────────────────────────────
        ws_v = f"Workspace: {view.workspace_name}"
        elapsed = view.elapsed_str()
        inner_pad = max(0, C - len(ws_v) - len(elapsed))
        ws_c = f"Workspace: {_BOLD}{view.workspace_name}{_RESET}"
        elapsed_c = f"{_DIM}{elapsed}{_RESET}"
        lines.append(f"{_V}  {ws_c}{' ' * inner_pad}{elapsed_c}  {_V}")

        # ── Recording indicator ────────────────────────────────────────
        dot = f"{_BRIGHT_GREEN}●{_RESET}"
        rec_c = f"Status: {dot} {_GREEN}RECORDING{_RESET}"
        lines.append(self._row(rec_c, W))

        # ── Separator ─────────────────────────────────────────────────
        lines.append(f"{_ML}{_H * H}{_MR}")

        # ── Browser section ───────────────────────────────────────────
        browser_tabs = view.browser_tabs
        if browser_tabs:
            for browser, tabs in browser_tabs.items():
                hdr = f"{_BOLD}Browser{_RESET}           {_CYAN}{browser}{_RESET}"
                lines.append(self._row(hdr, W))
                for i, tab in enumerate(tabs):
                    tree = "└─" if i == len(tabs) - 1 else "├─"
                    rel = _rel_time(tab.timestamp)
                    # tree(2) + space(1) = 3 prefix; trailing rel + 1 space = len(rel)+1
                    url_max = C - 3 - len(rel) - 1
                    url = _trunc(tab.url, max(url_max, 10))
                    gap = max(1, C - 3 - len(url) - len(rel))
                    row_c = (
                        f"{_DIM}{tree}{_RESET} {_GREEN}{url}{_RESET}"
                        f"{' ' * gap}{_DIM}{rel}{_RESET}"
                    )
                    lines.append(self._row(row_c, W))
        else:
            hdr = f"{_BOLD}Browser{_RESET}           {_DIM}not captured yet{_RESET}"
            lines.append(self._row(hdr, W))

        lines.append(self._blank(W))

        # ── IDE section ───────────────────────────────────────────────
        ide_projects = view.ide_projects
        if ide_projects:
            for client, projects in ide_projects.items():
                hdr = f"{_BOLD}IDE{_RESET}               {_CYAN}{client}{_RESET}"
                lines.append(self._row(hdr, W))
                for i, proj in enumerate(projects):
                    tree = "└─" if i == len(projects) - 1 else "├─"
                    label = "captured"
                    path_max = C - 3 - len(label) - 1
                    path = _trunc(proj.path, max(path_max, 10))
                    gap = max(1, C - 3 - len(path) - len(label))
                    row_c = (
                        f"{_DIM}{tree}{_RESET} {path}"
                        f"{' ' * gap}{_GREEN}{label}{_RESET}"
                    )
                    lines.append(self._row(row_c, W))
        else:
            hdr = f"{_BOLD}IDE{_RESET}               {_DIM}not captured yet{_RESET}"
            lines.append(self._row(hdr, W))

        lines.append(self._blank(W))

        # ── Terminal section ──────────────────────────────────────────
        terminal_sessions = view.terminal_sessions
        if terminal_sessions:
            for app, sessions in terminal_sessions.items():
                count = len(sessions)
                plural = "s" if count != 1 else ""
                app_label = f"{app} ({count} session{plural})"
                hdr = f"{_BOLD}Terminal{_RESET}          {_CYAN}{app_label}{_RESET}"
                lines.append(self._row(hdr, W))
                for i, sess in enumerate(sessions):
                    tree = "└─" if i == len(sessions) - 1 else "├─"
                    d = _trunc(sess.directory, C - 3)
                    gap = max(0, C - 3 - len(d))
                    row_c = f"{_DIM}{tree}{_RESET} {d}{' ' * gap}"
                    lines.append(self._row(row_c, W))
        else:
            hdr = f"{_BOLD}Terminal{_RESET}          {_DIM}not captured yet{_RESET}"
            lines.append(self._row(hdr, W))

        lines.append(self._blank(W))

        # ── VPN section ───────────────────────────────────────────────
        vpn_color = _GREEN if view.vpn_connected else _DIM
        vpn_c = f"{_BOLD}VPN{_RESET}               {vpn_color}{view.vpn_label}{_RESET}"
        lines.append(self._row(vpn_c, W))

        # ── Bottom border ─────────────────────────────────────────────
        lines.append(f"{_BL}{_H * H}{_BR}")

        # ── Footer hint ───────────────────────────────────────────────
        lines.append(
            f"  {_DIM}Press Ctrl+C or run `spaceload stop` to finish recording{_RESET}"
        )

        return lines
