"""Final static summary displayed after a recording session ends."""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from spaceload.tui.recording_view import RecordingView


def show_summary(workspace_name: str, view: "RecordingView", action_count: int) -> None:
    """Print a clean static summary of what was captured.

    This is intentionally plain text (no ANSI) so it remains readable
    when redirected to a file or when the terminal is scrolled back.
    """
    elapsed = view.elapsed_str()
    counts = view.summary_counts()

    out = sys.stdout.write

    out(f"\nRecording complete: {workspace_name}\n")
    out(f"Duration: {elapsed}\n")
    out("\nCaptured:\n")

    # Browser
    if counts["browser"]:
        for browser, count in counts["browser"].items():
            plural = "s" if count != 1 else ""
            out(f"  Browser tab{plural}:  {count} ({browser})\n")
    else:
        out("  Browser tabs:  none\n")

    # IDE
    if counts["ide"]:
        for client, count in counts["ide"].items():
            plural = "s" if count != 1 else ""
            out(f"  IDE:           {client} \u2014 {count} project{plural}\n")
    else:
        out("  IDE:           none\n")

    # Terminal
    tc = counts["terminal_count"]
    if tc:
        app = counts["terminal_app"] or "terminal"
        plural = "s" if tc != 1 else ""
        out(f"  Terminal{plural}:      {tc} session{plural} ({app})\n")
    else:
        out("  Terminals:     none\n")

    # VPN
    out(f"  VPN:           {counts['vpn']}\n")

    out(f"\nSaved {action_count} actions. Run it with: spaceload run {workspace_name}\n\n")
    sys.stdout.flush()
