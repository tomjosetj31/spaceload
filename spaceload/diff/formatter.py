"""Terminal formatter for DiffResult.

Renders a DiffResult as a color-coded diff to stdout. Degrades gracefully
when stdout is not a TTY or when the NO_COLOR environment variable is set.
"""

from __future__ import annotations

import os
import sys

from spaceload.diff.differ import DiffItem, DiffResult

# ANSI codes
_GREEN = "\033[32m"
_RED = "\033[31m"
_RESET = "\033[0m"
_BOLD = "\033[1m"
_DIM = "\033[2m"

_CATEGORY_TITLES = {
    "browser": "Browser tabs",
    "ide": "IDE",
    "terminal": "Terminals",
    "vpn": "VPN",
    "app": "Apps",
}

_STATUS_SUFFIX = {
    "added": "(new)",
    "removed": "(closed)",
    "unchanged": "(unchanged)",
}


def _use_color() -> bool:
    return sys.stdout.isatty() and "NO_COLOR" not in os.environ


def _colorize(text: str, color: str, use_color: bool) -> str:
    if not use_color:
        return text
    return f"{color}{text}{_RESET}"


def format_diff(
    result: DiffResult,
    old_name: str,
    new_name: str,
    *,
    file=None,
) -> None:
    """Print a formatted diff to *file* (defaults to stdout).

    Parameters
    ----------
    result:
        The DiffResult to render.
    old_name:
        Label for the baseline (e.g. workspace name).
    new_name:
        Label for the comparison (e.g. "current" or another workspace name).
    file:
        Output file-like object. Defaults to sys.stdout.
    """
    if file is None:
        file = sys.stdout

    color = _use_color()
    rule = "\u2500" * 42

    # Header
    header = f"Workspace diff: {old_name} \u2192 {new_name}"
    if color:
        header = f"{_BOLD}{header}{_RESET}"
    print(header, file=file)
    print(rule, file=file)
    print(file=file)

    # Group items by category, preserving the display order
    category_order = ["browser", "ide", "terminal", "vpn", "app"]
    grouped: dict[str, list[DiffItem]] = {c: [] for c in category_order}
    for item in result.items:
        if item.category in grouped:
            grouped[item.category].append(item)

    any_output = False
    for cat in category_order:
        cat_items = grouped[cat]
        if not cat_items:
            continue

        title = _CATEGORY_TITLES.get(cat, cat.capitalize())
        if color:
            title = f"{_BOLD}{title}{_RESET}"
        print(title, file=file)

        for item in cat_items:
            suffix = _STATUS_SUFFIX.get(item.status, "")
            if item.status == "added":
                symbol = "+"
                line = f"+ {item.label:<55} {suffix}"
                print(_colorize(line, _GREEN, color), file=file)
            elif item.status == "removed":
                symbol = "-"
                line = f"- {item.label:<55} {suffix}"
                print(_colorize(line, _RED, color), file=file)
            else:
                line = f"  {item.label:<55} {suffix}"
                if color:
                    line = f"{_DIM}{line}{_RESET}"
                print(line, file=file)

        print(file=file)
        any_output = True

    if not any_output:
        print("(no tracked resources found in either workspace)", file=file)
        print(file=file)

    print(rule, file=file)

    # Summary line
    parts = []
    if result.added:
        added_str = f"{result.added} added"
        parts.append(_colorize(added_str, _GREEN, color))
    if result.removed:
        removed_str = f"{result.removed} removed"
        parts.append(_colorize(removed_str, _RED, color))
    if result.unchanged:
        parts.append(f"{result.unchanged} unchanged")

    summary = "Summary: " + (", ".join(parts) if parts else "no changes")
    print(summary, file=file)
