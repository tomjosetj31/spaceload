"""Unit and integration tests for the AeroSpace adapter."""

from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

import pytest

from loadout.adapters.aerospace.adapter import (
    AeroSpaceAdapter,
    AeroWindow,
    BROWSER_APP_NAMES,
    IDE_APP_NAMES,
    TERMINAL_APP_NAMES,
)
from loadout.adapters.terminal.base import TerminalSession
from loadout.daemon.server import BrowserPoller, IDEPoller, TerminalPoller
from loadout.replayer.replayer import Replayer


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_proc(stdout="", returncode=0):
    m = MagicMock()
    m.stdout = stdout
    m.returncode = returncode
    return m


_SAMPLE_LIST_OUTPUT = """\
8861 4 Cursor
56 Q Firefox
1175 C Google Chrome
108 1 Microsoft Teams
60 2 Slack
8859 3 iTerm2
8843 3 iTerm2
"""


# ---------------------------------------------------------------------------
# AeroSpaceAdapter unit tests
# ---------------------------------------------------------------------------

class TestAeroSpaceAdapter:
    def setup_method(self):
        self.adapter = AeroSpaceAdapter()

    def test_is_available_when_binary_present(self):
        with patch("shutil.which", return_value="/usr/local/bin/aerospace"):
            assert self.adapter.is_available() is True

    def test_is_available_when_binary_missing(self):
        with patch("shutil.which", return_value=None):
            assert self.adapter.is_available() is False

    def test_list_windows_parses_output(self):
        with patch("subprocess.run", return_value=_make_proc(stdout=_SAMPLE_LIST_OUTPUT)):
            windows = self.adapter.list_windows()
        assert len(windows) == 7
        ids = [w.window_id for w in windows]
        assert 8861 in ids
        assert 56 in ids

    def test_list_windows_returns_correct_workspaces(self):
        with patch("subprocess.run", return_value=_make_proc(stdout=_SAMPLE_LIST_OUTPUT)):
            windows = self.adapter.list_windows()
        by_id = {w.window_id: w for w in windows}
        assert by_id[8861].workspace == "4"
        assert by_id[56].workspace == "Q"
        assert by_id[1175].workspace == "C"
        assert by_id[8859].workspace == "3"

    def test_list_windows_returns_correct_app_names(self):
        with patch("subprocess.run", return_value=_make_proc(stdout=_SAMPLE_LIST_OUTPUT)):
            windows = self.adapter.list_windows()
        by_id = {w.window_id: w for w in windows}
        assert by_id[108].app_name == "Microsoft Teams"
        assert by_id[60].app_name == "Slack"

    def test_list_windows_returns_empty_on_failure(self):
        with patch("subprocess.run", return_value=_make_proc(returncode=1)):
            assert self.adapter.list_windows() == []

    def test_list_windows_returns_empty_on_blank_output(self):
        with patch("subprocess.run", return_value=_make_proc(stdout="")):
            assert self.adapter.list_windows() == []

    def test_get_app_workspace_returns_correct_workspace(self):
        with patch("subprocess.run", return_value=_make_proc(stdout=_SAMPLE_LIST_OUTPUT)):
            ws = self.adapter.get_app_workspace("Google Chrome")
        assert ws == "C"

    def test_get_app_workspace_returns_first_match(self):
        with patch("subprocess.run", return_value=_make_proc(stdout=_SAMPLE_LIST_OUTPUT)):
            ws = self.adapter.get_app_workspace("iTerm2")
        assert ws == "3"

    def test_get_app_workspace_returns_none_for_unknown(self):
        with patch("subprocess.run", return_value=_make_proc(stdout=_SAMPLE_LIST_OUTPUT)):
            assert self.adapter.get_app_workspace("Vim") is None

    def test_get_app_window_ids(self):
        with patch("subprocess.run", return_value=_make_proc(stdout=_SAMPLE_LIST_OUTPUT)):
            ids = self.adapter.get_app_window_ids("iTerm2")
        assert set(ids) == {8859, 8843}

    def test_get_app_window_ids_empty_for_unknown(self):
        with patch("subprocess.run", return_value=_make_proc(stdout=_SAMPLE_LIST_OUTPUT)):
            assert self.adapter.get_app_window_ids("Vim") == []

    def test_move_window_to_workspace_success(self):
        with patch("subprocess.run", return_value=_make_proc(returncode=0)) as mock_run:
            result = self.adapter.move_window_to_workspace(8861, "3")
        assert result is True
        args = mock_run.call_args[0][0]
        assert "aerospace" in args
        assert "move-node-to-workspace" in args
        assert "--window-id" in args
        assert "8861" in args
        assert "3" in args

    def test_move_window_to_workspace_failure(self):
        with patch("subprocess.run", return_value=_make_proc(returncode=1)):
            assert self.adapter.move_window_to_workspace(999, "X") is False

    def test_move_app_to_workspace_moves_first_window(self):
        with patch.object(
            self.adapter, "list_windows",
            return_value=[
                AeroWindow(window_id=8859, workspace="3", app_name="iTerm2"),
                AeroWindow(window_id=8843, workspace="3", app_name="iTerm2"),
            ]
        ), patch.object(self.adapter, "move_window_to_workspace", return_value=True) as mock_move:
            result = self.adapter.move_app_to_workspace("iTerm2", "4")
        assert result is True
        mock_move.assert_called_once_with(8859, "4")

    def test_move_app_to_workspace_fails_when_app_not_found(self):
        with patch.object(self.adapter, "list_windows", return_value=[]):
            assert self.adapter.move_app_to_workspace("Vim", "4") is False


# ---------------------------------------------------------------------------
# App name mapping tables
# ---------------------------------------------------------------------------

class TestAppNameMappings:
    def test_browser_mappings_present(self):
        assert BROWSER_APP_NAMES["chrome"] == "Google Chrome"
        assert BROWSER_APP_NAMES["safari"] == "Safari"
        assert BROWSER_APP_NAMES["arc"] == "Arc"

    def test_ide_mappings_present(self):
        assert IDE_APP_NAMES["vscode"] == "Code"
        assert IDE_APP_NAMES["cursor"] == "Cursor"
        assert IDE_APP_NAMES["zed"] == "Zed"

    def test_terminal_mappings_present(self):
        assert TERMINAL_APP_NAMES["iterm2"] == "iTerm2"
        assert TERMINAL_APP_NAMES["terminal"] == "Terminal"
        assert TERMINAL_APP_NAMES["warp"] == "Warp"
        assert TERMINAL_APP_NAMES["kitty"] == "kitty"


# ---------------------------------------------------------------------------
# Poller workspace enrichment tests
# ---------------------------------------------------------------------------

class TestBrowserPollerWorkspaceEnrichment:
    def test_workspace_added_to_browser_tab_open_event(self):
        actions: list[dict] = []
        # Use short stabilization time for tests
        poller = BrowserPoller(actions, poll_interval=0.05, stabilization_time=0.1, domain_cooldown=0.1)

        call_count = 0

        def fake_available_adapters():
            nonlocal call_count
            adapter = MagicMock()
            adapter.name = "chrome"
            call_count += 1
            if call_count == 1:
                adapter.get_open_tabs.return_value = []
            else:
                adapter.get_open_tabs.return_value = ["https://github.com"]
            return [adapter]

        mock_registry = MagicMock()
        mock_registry.available_adapters.side_effect = fake_available_adapters

        mock_aerospace = MagicMock()
        mock_aerospace.get_app_workspace.return_value = "C"

        mock_wm = MagicMock()
        mock_wm.get_app_workspace.return_value = "C"

        with patch("loadout.daemon.server.BrowserAdapterRegistry", return_value=mock_registry), \
             patch("loadout.daemon.server.WorkspaceManagerRegistry") as mock_reg_cls:
            mock_reg_cls.return_value.detect_active.return_value = mock_wm
            poller.start()
            time.sleep(0.4)  # Wait for stabilization
            poller.stop()

        open_actions = [a for a in actions if a.get("type") == "browser_tab_open"]
        assert open_actions
        assert open_actions[0].get("workspace") == "C"

    def test_workspace_omitted_when_no_wm_available(self):
        actions: list[dict] = []
        # Use short stabilization time for tests
        poller = BrowserPoller(actions, poll_interval=0.05, stabilization_time=0.1, domain_cooldown=0.1)

        call_count = 0

        def fake_available_adapters():
            nonlocal call_count
            adapter = MagicMock()
            adapter.name = "chrome"
            call_count += 1
            if call_count == 1:
                adapter.get_open_tabs.return_value = []
            else:
                adapter.get_open_tabs.return_value = ["https://github.com"]
            return [adapter]

        mock_registry = MagicMock()
        mock_registry.available_adapters.side_effect = fake_available_adapters

        with patch("loadout.daemon.server.BrowserAdapterRegistry", return_value=mock_registry), \
             patch("loadout.daemon.server.WorkspaceManagerRegistry") as mock_reg_cls:
            mock_reg_cls.return_value.detect_active.return_value = None
            poller.start()
            time.sleep(0.4)  # Wait for stabilization
            poller.stop()

        open_actions = [a for a in actions if a.get("type") == "browser_tab_open"]
        assert open_actions
        assert "workspace" not in open_actions[0]


class TestIDEPollerWorkspaceEnrichment:
    def test_workspace_added_to_ide_project_open_event(self):
        actions: list[dict] = []
        poller = IDEPoller(actions, poll_interval=0.05)

        call_count = 0

        def fake_available_adapters():
            nonlocal call_count
            adapter = MagicMock()
            adapter.name = "cursor"
            call_count += 1
            if call_count == 1:
                adapter.get_open_projects.return_value = []
            else:
                adapter.get_open_projects.return_value = ["/home/user/project"]
            return [adapter]

        mock_registry = MagicMock()
        mock_registry.available_adapters.side_effect = fake_available_adapters

        mock_wm = MagicMock()
        mock_wm.get_app_workspace.return_value = "4"

        with patch("loadout.daemon.server.IDEAdapterRegistry", return_value=mock_registry), \
             patch("loadout.daemon.server.WorkspaceManagerRegistry") as mock_reg_cls:
            mock_reg_cls.return_value.detect_active.return_value = mock_wm
            poller.start()
            time.sleep(0.3)
            poller.stop()

        open_actions = [a for a in actions if a.get("type") == "ide_project_open"]
        assert open_actions
        assert open_actions[0].get("workspace") == "4"


class TestTerminalPollerWorkspaceEnrichment:
    def test_workspace_added_to_terminal_session_open_event(self):
        actions: list[dict] = []
        poller = TerminalPoller(actions, poll_interval=0.05)

        call_count = 0

        def fake_available_adapters():
            nonlocal call_count
            adapter = MagicMock()
            adapter.name = "iterm2"
            call_count += 1
            if call_count == 1:
                adapter.get_sessions.return_value = []
            else:
                adapter.get_sessions.return_value = [
                    TerminalSession(app="iterm2", directory="/home/user/projects", session_id="/dev/ttys001")
                ]
            return [adapter]

        mock_registry = MagicMock()
        mock_registry.available_adapters.side_effect = fake_available_adapters

        mock_wm = MagicMock()
        mock_wm.get_app_workspace.return_value = "3"

        with patch("loadout.daemon.server.TerminalAdapterRegistry", return_value=mock_registry), \
             patch("loadout.daemon.server.WorkspaceManagerRegistry") as mock_reg_cls:
            mock_reg_cls.return_value.detect_active.return_value = mock_wm
            poller.start()
            time.sleep(0.3)
            poller.stop()

        open_actions = [a for a in actions if a.get("type") == "terminal_session_open"]
        assert open_actions
        assert open_actions[0].get("workspace") == "3"


# ---------------------------------------------------------------------------
# Replayer workspace placement tests
# ---------------------------------------------------------------------------

class TestReplayerWorkspacePlacement:
    def test_browser_tab_open_moves_to_workspace(self, capsys):
        mock_browser_adapter = MagicMock()
        mock_browser_adapter.open_url.return_value = True
        mock_browser_registry = MagicMock()
        mock_browser_registry.get_adapter.return_value = mock_browser_adapter

        mock_aerospace = MagicMock()
        mock_aerospace.move_app_to_workspace.return_value = True

        actions = [{
            "type": "browser_tab_open",
            "browser": "chrome",
            "url": "https://github.com",
            "workspace": "C",
            "timestamp": "2026-01-01T00:00:00+00:00",
        }]
        replayer = Replayer("test", actions)
        replayer._browser_registry = mock_browser_registry
        replayer._aerospace = mock_aerospace

        with patch("loadout.replayer.replayer.time.sleep"):
            replayer.replay()

        mock_aerospace.move_app_to_workspace.assert_called_once_with("Google Chrome", "C")
        captured = capsys.readouterr()
        assert "workspace" in captured.out

    def test_browser_tab_open_no_workspace_skips_aerospace(self, capsys):
        mock_browser_adapter = MagicMock()
        mock_browser_adapter.open_url.return_value = True
        mock_browser_registry = MagicMock()
        mock_browser_registry.get_adapter.return_value = mock_browser_adapter

        mock_aerospace = MagicMock()

        actions = [{
            "type": "browser_tab_open",
            "browser": "chrome",
            "url": "https://github.com",
            "timestamp": "2026-01-01T00:00:00+00:00",
        }]
        replayer = Replayer("test", actions)
        replayer._browser_registry = mock_browser_registry
        replayer._aerospace = mock_aerospace

        replayer.replay()

        mock_aerospace.move_app_to_workspace.assert_not_called()

    def test_ide_project_open_moves_to_workspace(self, capsys):
        mock_ide_adapter = MagicMock()
        mock_ide_adapter.open_project.return_value = True
        mock_ide_registry = MagicMock()
        mock_ide_registry.get_adapter.return_value = mock_ide_adapter

        mock_aerospace = MagicMock()
        mock_aerospace.move_app_to_workspace.return_value = True

        actions = [{
            "type": "ide_project_open",
            "client": "cursor",
            "path": "/home/user/project",
            "workspace": "4",
            "timestamp": "2026-01-01T00:00:00+00:00",
        }]
        replayer = Replayer("test", actions)
        replayer._ide_registry = mock_ide_registry
        replayer._aerospace = mock_aerospace

        with patch("loadout.replayer.replayer.time.sleep"):
            replayer.replay()

        mock_aerospace.move_app_to_workspace.assert_called_once_with("Cursor", "4")

    def test_terminal_session_open_moves_new_window_to_workspace(self, capsys):
        mock_terminal_adapter = MagicMock()
        mock_terminal_adapter.open_in_dir.return_value = True
        mock_terminal_registry = MagicMock()
        mock_terminal_registry.get_adapter.return_value = mock_terminal_adapter

        mock_aerospace = MagicMock()
        # Before: window 100 exists. After: windows 100 and 200 exist.
        mock_aerospace.get_app_window_ids.side_effect = [[100], [100, 200]]
        mock_aerospace.move_window_to_workspace.return_value = True

        actions = [{
            "type": "terminal_session_open",
            "app": "iterm2",
            "directory": "/home/user/projects",
            "workspace": "3",
            "timestamp": "2026-01-01T00:00:00+00:00",
        }]
        replayer = Replayer("test", actions)
        replayer._terminal_registry = mock_terminal_registry
        replayer._aerospace = mock_aerospace

        with patch("loadout.replayer.replayer.time.sleep"):
            replayer.replay()

        # Should move only the new window (200) to workspace 3
        mock_aerospace.move_window_to_workspace.assert_called_once_with(200, "3")

    def test_terminal_session_open_no_workspace_skips_aerospace(self):
        mock_terminal_adapter = MagicMock()
        mock_terminal_adapter.open_in_dir.return_value = True
        mock_terminal_registry = MagicMock()
        mock_terminal_registry.get_adapter.return_value = mock_terminal_adapter

        mock_aerospace = MagicMock()

        actions = [{
            "type": "terminal_session_open",
            "app": "iterm2",
            "directory": "/home/user/projects",
            "timestamp": "2026-01-01T00:00:00+00:00",
        }]
        replayer = Replayer("test", actions)
        replayer._terminal_registry = mock_terminal_registry
        replayer._aerospace = mock_aerospace

        replayer.replay()

        mock_aerospace.move_window_to_workspace.assert_not_called()

    def test_aerospace_unavailable_skips_placement(self, capsys):
        mock_browser_adapter = MagicMock()
        mock_browser_adapter.open_url.return_value = True
        mock_browser_registry = MagicMock()
        mock_browser_registry.get_adapter.return_value = mock_browser_adapter

        actions = [{
            "type": "browser_tab_open",
            "browser": "chrome",
            "url": "https://github.com",
            "workspace": "C",
            "timestamp": "2026-01-01T00:00:00+00:00",
        }]
        replayer = Replayer("test", actions)
        replayer._browser_registry = mock_browser_registry
        replayer._aerospace = None  # AeroSpace not available

        replayer.replay()
        # Should not raise; workspace placement silently skipped
        captured = capsys.readouterr()
        assert "ok" in captured.out
