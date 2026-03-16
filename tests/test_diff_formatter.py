"""Tests for spaceload.diff.formatter."""

from __future__ import annotations

import io
import os
from unittest.mock import patch

from spaceload.diff.differ import DiffItem, DiffResult
from spaceload.diff.formatter import format_diff


def _result(*items: DiffItem) -> DiffResult:
    added = sum(1 for i in items if i.status == "added")
    removed = sum(1 for i in items if i.status == "removed")
    unchanged = sum(1 for i in items if i.status == "unchanged")
    return DiffResult(list(items), added=added, removed=removed, unchanged=unchanged)


def _item(category: str, status: str, label: str) -> DiffItem:
    return DiffItem(category=category, status=status, label=label)


class TestFormatterSymbols:
    def _render(self, result: DiffResult, color: bool = False) -> str:
        buf = io.StringIO()
        with patch("spaceload.diff.formatter._use_color", return_value=color):
            format_diff(result, "workspace-a", "current", file=buf)
        return buf.getvalue()

    def test_added_line_has_plus(self):
        result = _result(_item("browser", "added", "chrome: https://new.com"))
        output = self._render(result)
        assert any(line.startswith("+ ") for line in output.splitlines())

    def test_removed_line_has_minus(self):
        result = _result(_item("browser", "removed", "chrome: https://old.com"))
        output = self._render(result)
        assert any(line.startswith("- ") for line in output.splitlines())

    def test_unchanged_line_has_space_prefix(self):
        result = _result(_item("browser", "unchanged", "chrome: https://same.com"))
        output = self._render(result)
        assert any(line.startswith("  ") for line in output.splitlines())

    def test_header_contains_both_names(self):
        result = _result(_item("browser", "added", "https://x.com"))
        output = self._render(result)
        assert "workspace-a" in output
        assert "current" in output

    def test_summary_shows_added(self):
        result = _result(_item("browser", "added", "https://x.com"))
        output = self._render(result)
        assert "1 added" in output

    def test_summary_shows_removed(self):
        result = _result(_item("browser", "removed", "https://x.com"))
        output = self._render(result)
        assert "1 removed" in output

    def test_summary_shows_unchanged(self):
        result = _result(_item("browser", "unchanged", "https://x.com"))
        output = self._render(result)
        assert "1 unchanged" in output

    def test_empty_result_shows_no_tracked_resources(self):
        result = DiffResult()
        output = self._render(result)
        assert "no tracked resources" in output.lower()

    def test_no_color_no_ansi_codes(self):
        result = _result(_item("browser", "added", "https://x.com"))
        output = self._render(result, color=False)
        assert "\033[" not in output

    def test_category_title_browser_shown(self):
        result = _result(_item("browser", "added", "chrome: https://x.com"))
        output = self._render(result)
        assert "Browser tabs" in output

    def test_category_title_ide_shown(self):
        result = _result(_item("ide", "added", "vscode \u2192 /project"))
        output = self._render(result)
        assert "IDE" in output

    def test_category_title_terminal_shown(self):
        result = _result(_item("terminal", "added", "iterm2: /home"))
        output = self._render(result)
        assert "Terminals" in output


class TestNoColorEnvironment:
    def test_no_color_env_disables_ansi(self):
        result = _result(_item("browser", "added", "https://x.com"))
        buf = io.StringIO()
        with patch.dict(os.environ, {"NO_COLOR": "1"}):
            with patch("sys.stdout.isatty", return_value=True):
                format_diff(result, "a", "b", file=buf)
        assert "\033[" not in buf.getvalue()
