"""Unit tests for the workspace manager (WM) adapter layer."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from ctx.adapters.wm.base import WMWindow, WorkspaceManagerAdapter
from ctx.adapters.wm.aerospace import AeroSpaceAdapter
from ctx.adapters.wm.yabai import YabaiAdapter
from ctx.adapters.wm.registry import WorkspaceManagerRegistry
from ctx.adapters.wm.app_names import BROWSER_APP_NAMES, IDE_APP_NAMES, TERMINAL_APP_NAMES


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _proc(stdout="", returncode=0):
    m = MagicMock()
    m.stdout = stdout
    m.returncode = returncode
    return m


_AEROSPACE_OUTPUT = """\
8861 4 Cursor
56 Q Firefox
1175 C Google Chrome
108 1 Microsoft Teams
60 2 Slack
8859 3 iTerm2
8843 3 iTerm2
"""

_YABAI_OUTPUT = json.dumps([
    {"id": 101, "app": "iTerm2",          "title": "~",          "space": 3},
    {"id": 102, "app": "Google Chrome",   "title": "GitHub",     "space": 2},
    {"id": 103, "app": "Cursor",          "title": "ctx",        "space": 4},
    {"id": 104, "app": "Slack",           "title": "kotaicode",  "space": 1},
    {"id": 105, "app": "iTerm2",          "title": "server",     "space": 3},
])


# ---------------------------------------------------------------------------
# WMWindow dataclass
# ---------------------------------------------------------------------------

class TestWMWindow:
    def test_fields(self):
        w = WMWindow(window_id=42, workspace="3", app_name="iTerm2")
        assert w.window_id == 42
        assert w.workspace == "3"
        assert w.app_name == "iTerm2"


# ---------------------------------------------------------------------------
# AeroSpaceAdapter
# ---------------------------------------------------------------------------

class TestAeroSpaceAdapter:
    def setup_method(self):
        self.adapter = AeroSpaceAdapter()

    def test_name(self):
        assert self.adapter.name == "aerospace"

    def test_is_available_true(self):
        with patch("shutil.which", return_value="/usr/local/bin/aerospace"):
            assert self.adapter.is_available() is True

    def test_is_available_false(self):
        with patch("shutil.which", return_value=None):
            assert self.adapter.is_available() is False

    def test_list_windows_parses_correctly(self):
        with patch("subprocess.run", return_value=_proc(stdout=_AEROSPACE_OUTPUT)):
            windows = self.adapter.list_windows()
        assert len(windows) == 7
        by_id = {w.window_id: w for w in windows}
        assert by_id[8861].workspace == "4"
        assert by_id[8861].app_name == "Cursor"
        assert by_id[1175].workspace == "C"
        assert by_id[1175].app_name == "Google Chrome"

    def test_list_windows_multiple_same_app(self):
        with patch("subprocess.run", return_value=_proc(stdout=_AEROSPACE_OUTPUT)):
            windows = self.adapter.list_windows()
        iterm_windows = [w for w in windows if w.app_name == "iTerm2"]
        assert len(iterm_windows) == 2

    def test_list_windows_empty_on_failure(self):
        with patch("subprocess.run", return_value=_proc(returncode=1)):
            assert self.adapter.list_windows() == []

    def test_list_windows_empty_on_blank_output(self):
        with patch("subprocess.run", return_value=_proc(stdout="")):
            assert self.adapter.list_windows() == []

    def test_get_app_workspace(self):
        with patch("subprocess.run", return_value=_proc(stdout=_AEROSPACE_OUTPUT)):
            assert self.adapter.get_app_workspace("Slack") == "2"

    def test_get_app_workspace_none_for_unknown(self):
        with patch("subprocess.run", return_value=_proc(stdout=_AEROSPACE_OUTPUT)):
            assert self.adapter.get_app_workspace("Vim") is None

    def test_get_app_window_ids(self):
        with patch("subprocess.run", return_value=_proc(stdout=_AEROSPACE_OUTPUT)):
            ids = self.adapter.get_app_window_ids("iTerm2")
        assert set(ids) == {8859, 8843}

    def test_move_window_to_workspace_success(self):
        with patch("subprocess.run", return_value=_proc(returncode=0)) as mock_run:
            assert self.adapter.move_window_to_workspace(8861, "3") is True
        args = mock_run.call_args[0][0]
        assert "aerospace" in args
        assert "move-node-to-workspace" in args
        assert "--window-id" in args
        assert "8861" in args
        assert "3" in args

    def test_move_window_to_workspace_failure(self):
        with patch("subprocess.run", return_value=_proc(returncode=1)):
            assert self.adapter.move_window_to_workspace(999, "X") is False

    def test_move_app_to_workspace(self):
        with patch.object(
            self.adapter, "list_windows",
            return_value=[WMWindow(8859, "3", "iTerm2"), WMWindow(8843, "3", "iTerm2")]
        ), patch.object(self.adapter, "move_window_to_workspace", return_value=True) as mv:
            assert self.adapter.move_app_to_workspace("iTerm2", "4") is True
        mv.assert_called_once_with(8859, "4")

    def test_move_app_to_workspace_fails_when_not_found(self):
        with patch.object(self.adapter, "list_windows", return_value=[]):
            assert self.adapter.move_app_to_workspace("Vim", "4") is False


# ---------------------------------------------------------------------------
# YabaiAdapter
# ---------------------------------------------------------------------------

class TestYabaiAdapter:
    def setup_method(self):
        self.adapter = YabaiAdapter()

    def test_name(self):
        assert self.adapter.name == "yabai"

    def test_is_available_true(self):
        with patch("shutil.which", return_value="/usr/local/bin/yabai"):
            assert self.adapter.is_available() is True

    def test_is_available_false(self):
        with patch("shutil.which", return_value=None):
            assert self.adapter.is_available() is False

    def test_list_windows_parses_json(self):
        with patch("subprocess.run", return_value=_proc(stdout=_YABAI_OUTPUT)):
            windows = self.adapter.list_windows()
        assert len(windows) == 5
        by_id = {w.window_id: w for w in windows}
        assert by_id[101].workspace == "3"
        assert by_id[101].app_name == "iTerm2"
        assert by_id[102].workspace == "2"
        assert by_id[102].app_name == "Google Chrome"

    def test_list_windows_space_stored_as_string(self):
        """Yabai returns space as int; adapter converts to str for uniformity."""
        with patch("subprocess.run", return_value=_proc(stdout=_YABAI_OUTPUT)):
            windows = self.adapter.list_windows()
        for w in windows:
            assert isinstance(w.workspace, str)

    def test_list_windows_empty_on_failure(self):
        with patch("subprocess.run", return_value=_proc(returncode=1)):
            assert self.adapter.list_windows() == []

    def test_list_windows_empty_on_invalid_json(self):
        with patch("subprocess.run", return_value=_proc(stdout="not json")):
            assert self.adapter.list_windows() == []

    def test_get_app_workspace(self):
        with patch("subprocess.run", return_value=_proc(stdout=_YABAI_OUTPUT)):
            assert self.adapter.get_app_workspace("Cursor") == "4"

    def test_get_app_workspace_returns_first_match(self):
        with patch("subprocess.run", return_value=_proc(stdout=_YABAI_OUTPUT)):
            assert self.adapter.get_app_workspace("iTerm2") == "3"

    def test_get_app_workspace_none_for_unknown(self):
        with patch("subprocess.run", return_value=_proc(stdout=_YABAI_OUTPUT)):
            assert self.adapter.get_app_workspace("Vim") is None

    def test_get_app_window_ids(self):
        with patch("subprocess.run", return_value=_proc(stdout=_YABAI_OUTPUT)):
            ids = self.adapter.get_app_window_ids("iTerm2")
        assert set(ids) == {101, 105}

    def test_move_window_to_workspace_success(self):
        with patch("subprocess.run", return_value=_proc(returncode=0)) as mock_run:
            assert self.adapter.move_window_to_workspace(101, "2") is True
        args = mock_run.call_args[0][0]
        assert "yabai" in args
        assert "-m" in args
        assert "window" in args
        assert "101" in args
        assert "--space" in args
        assert "2" in args

    def test_move_window_to_workspace_failure(self):
        with patch("subprocess.run", return_value=_proc(returncode=1)):
            assert self.adapter.move_window_to_workspace(999, "5") is False

    def test_move_app_to_workspace(self):
        with patch.object(
            self.adapter, "list_windows",
            return_value=[WMWindow(101, "3", "iTerm2"), WMWindow(105, "3", "iTerm2")]
        ), patch.object(self.adapter, "move_window_to_workspace", return_value=True) as mv:
            assert self.adapter.move_app_to_workspace("iTerm2", "1") is True
        mv.assert_called_once_with(101, "1")


# ---------------------------------------------------------------------------
# WorkspaceManagerRegistry
# ---------------------------------------------------------------------------

class TestWorkspaceManagerRegistry:
    def test_detect_active_returns_first_available(self):
        registry = WorkspaceManagerRegistry()
        mock_a = MagicMock()
        mock_a.is_available.return_value = True
        mock_b = MagicMock()
        mock_b.is_available.return_value = True
        registry._adapters = [mock_a, mock_b]
        assert registry.detect_active() is mock_a

    def test_detect_active_skips_unavailable(self):
        registry = WorkspaceManagerRegistry()
        mock_a = MagicMock()
        mock_a.is_available.return_value = False
        mock_b = MagicMock()
        mock_b.is_available.return_value = True
        registry._adapters = [mock_a, mock_b]
        assert registry.detect_active() is mock_b

    def test_detect_active_returns_none_when_none_available(self):
        registry = WorkspaceManagerRegistry()
        with patch("shutil.which", return_value=None):
            assert registry.detect_active() is None

    def test_get_adapter_aerospace(self):
        registry = WorkspaceManagerRegistry()
        assert registry.get_adapter("aerospace").name == "aerospace"

    def test_get_adapter_yabai(self):
        registry = WorkspaceManagerRegistry()
        assert registry.get_adapter("yabai").name == "yabai"

    def test_get_adapter_unknown_returns_none(self):
        registry = WorkspaceManagerRegistry()
        assert registry.get_adapter("i3") is None

    def test_available_adapters_filters(self):
        registry = WorkspaceManagerRegistry()
        mock_a = MagicMock()
        mock_a.is_available.return_value = True
        mock_b = MagicMock()
        mock_b.is_available.return_value = False
        registry._adapters = [mock_a, mock_b]
        assert registry.available_adapters() == [mock_a]


# ---------------------------------------------------------------------------
# App name mapping tables
# ---------------------------------------------------------------------------

class TestAppNameMappings:
    def test_browser_mappings(self):
        assert BROWSER_APP_NAMES["chrome"] == "Google Chrome"
        assert BROWSER_APP_NAMES["safari"] == "Safari"
        assert BROWSER_APP_NAMES["arc"] == "Arc"
        assert BROWSER_APP_NAMES["firefox"] == "Firefox"

    def test_ide_mappings(self):
        assert IDE_APP_NAMES["vscode"] == "Code"
        assert IDE_APP_NAMES["cursor"] == "Cursor"
        assert IDE_APP_NAMES["zed"] == "Zed"

    def test_terminal_mappings(self):
        assert TERMINAL_APP_NAMES["iterm2"] == "iTerm2"
        assert TERMINAL_APP_NAMES["terminal"] == "Terminal"
        assert TERMINAL_APP_NAMES["warp"] == "Warp"
        assert TERMINAL_APP_NAMES["kitty"] == "kitty"
