"""Tests for spaceload.diff.differ — pure diff engine."""

from __future__ import annotations

from spaceload.diff.differ import DiffItem, DiffResult, diff


def _browser(url: str, browser: str = "chrome") -> dict:
    return {"type": "browser_tab_open", "browser": browser, "url": url, "timestamp": "t"}


def _ide(path: str, client: str = "vscode") -> dict:
    return {"type": "ide_project_open", "client": client, "path": path, "timestamp": "t"}


def _terminal(directory: str, app: str = "iterm2") -> dict:
    return {"type": "terminal_session_open", "app": app, "directory": directory, "session_id": f"{app}:{directory}", "timestamp": "t"}


def _vpn(client: str = "tailscale", profile: str | None = None) -> dict:
    return {"type": "vpn_connect", "client": client, "profile": profile, "timestamp": "t"}


def _app(name: str) -> dict:
    return {"type": "app_open", "app_name": name, "timestamp": "t"}


class TestDifferBasics:
    def test_returns_diff_result(self):
        result = diff([], [])
        assert isinstance(result, DiffResult)

    def test_empty_lists_produce_no_items(self):
        result = diff([], [])
        assert result.items == []
        assert result.added == 0
        assert result.removed == 0
        assert result.unchanged == 0

    def test_is_pure_no_side_effects(self):
        old = [_browser("https://example.com")]
        new = [_browser("https://github.com")]
        old_copy = list(old)
        new_copy = list(new)
        diff(old, new)
        assert old == old_copy
        assert new == new_copy


class TestBrowserDiff:
    def test_added_tab(self):
        result = diff([], [_browser("https://new.com")])
        added = [i for i in result.items if i.status == "added"]
        assert len(added) == 1
        assert "https://new.com" in added[0].label
        assert result.added == 1

    def test_removed_tab(self):
        result = diff([_browser("https://old.com")], [])
        removed = [i for i in result.items if i.status == "removed"]
        assert len(removed) == 1
        assert "https://old.com" in removed[0].label
        assert result.removed == 1

    def test_unchanged_tab(self):
        result = diff([_browser("https://same.com")], [_browser("https://same.com")])
        unchanged = [i for i in result.items if i.status == "unchanged"]
        assert len(unchanged) == 1
        assert result.unchanged == 1

    def test_mixed_tabs(self):
        old = [_browser("https://kept.com"), _browser("https://gone.com")]
        new = [_browser("https://kept.com"), _browser("https://new.com")]
        result = diff(old, new)
        assert result.added == 1
        assert result.removed == 1
        assert result.unchanged == 1

    def test_tab_category_is_browser(self):
        result = diff([], [_browser("https://x.com")])
        assert all(i.category == "browser" for i in result.items)


class TestIDEDiff:
    def test_added_project(self):
        result = diff([], [_ide("/Users/tom/code/new")])
        added = [i for i in result.items if i.status == "added"]
        assert len(added) == 1
        assert "/Users/tom/code/new" in added[0].label
        assert result.added == 1

    def test_removed_project(self):
        result = diff([_ide("/Users/tom/code/old")], [])
        removed = [i for i in result.items if i.status == "removed"]
        assert len(removed) == 1
        assert result.removed == 1

    def test_changed_path(self):
        old = [_ide("/Users/tom/code/payments")]
        new = [_ide("/Users/tom/code/billing")]
        result = diff(old, new)
        assert result.added == 1
        assert result.removed == 1
        assert result.unchanged == 0

    def test_unchanged_project(self):
        result = diff([_ide("/Users/tom/code/same")], [_ide("/Users/tom/code/same")])
        assert result.unchanged == 1

    def test_ide_label_contains_arrow(self):
        result = diff([], [_ide("/project")])
        assert "\u2192" in result.items[0].label


class TestTerminalDiff:
    def test_added_session(self):
        result = diff([], [_terminal("/Users/tom/code")])
        added = [i for i in result.items if i.status == "added"]
        assert len(added) == 1
        assert result.added == 1

    def test_removed_session(self):
        result = diff([_terminal("/Users/tom/old")], [])
        assert result.removed == 1

    def test_unchanged_session(self):
        result = diff([_terminal("/same")], [_terminal("/same")])
        assert result.unchanged == 1


class TestVPNDiff:
    def test_added_vpn(self):
        result = diff([], [_vpn("tailscale")])
        assert result.added == 1

    def test_removed_vpn(self):
        result = diff([_vpn("tailscale")], [])
        assert result.removed == 1

    def test_unchanged_vpn(self):
        result = diff([_vpn("tailscale")], [_vpn("tailscale")])
        assert result.unchanged == 1

    def test_vpn_with_profile(self):
        result = diff([], [_vpn("tailscale", "work")])
        added = [i for i in result.items if i.status == "added"]
        assert len(added) == 1
        assert "tailscale" in added[0].label


class TestSummaryCounts:
    def test_counts_are_accurate(self):
        old = [
            _browser("https://kept.com"),
            _browser("https://gone.com"),
            _ide("/kept-project"),
        ]
        new = [
            _browser("https://kept.com"),
            _browser("https://added.com"),
            _ide("/kept-project"),
        ]
        result = diff(old, new)
        assert result.added == 1
        assert result.removed == 1
        assert result.unchanged == 2
        assert result.total == 4

    def test_total_equals_sum_of_counts(self):
        old = [_browser("https://a.com"), _browser("https://b.com")]
        new = [_browser("https://b.com"), _browser("https://c.com")]
        result = diff(old, new)
        assert result.total == result.added + result.removed + result.unchanged
