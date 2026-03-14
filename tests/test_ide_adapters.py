"""Unit tests for IDE adapters (mocked subprocess and filesystem calls)."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from loadout.adapters.ide.base import IDEAdapter, ProjectSet
from loadout.adapters.ide.vscode import VSCodeAdapter, _get_projects_from_storage as _get_vscode_projects
from loadout.adapters.ide.cursor import CursorAdapter, _get_projects_from_storage as _get_cursor_projects
from loadout.adapters.ide.zed import ZedAdapter
from loadout.adapters.ide.registry import IDEAdapterRegistry


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_completed_process(returncode=0):
    mock = MagicMock()
    mock.returncode = returncode
    return mock


def _make_legacy_storage_json(paths: list[str]) -> str:
    """Create storage.json with legacy workspaces3 format."""
    workspaces = [{"folderUri": f"file://{p}"} for p in paths]
    return json.dumps({"openedPathsList": {"workspaces3": workspaces}})


def _make_windows_state_storage_json(paths: list[str]) -> str:
    """Create storage.json with modern windowsState format."""
    if not paths:
        return json.dumps({"windowsState": {}})
    
    # First path goes in lastActiveWindow, rest in openedWindows
    last_window = {"folder": f"file://{paths[0]}"}
    opened_windows = [{"folder": f"file://{p}"} for p in paths[1:]]
    
    return json.dumps({
        "windowsState": {
            "lastActiveWindow": last_window,
            "openedWindows": opened_windows
        }
    })


# ---------------------------------------------------------------------------
# _get_projects_from_storage helper (VS Code)
# ---------------------------------------------------------------------------

class TestGetVscodeProjects:
    def test_returns_paths_from_windows_state(self, tmp_path):
        # Note: The adapter no longer validates path existence since remote paths can't be checked
        storage = tmp_path / "storage.json"
        storage.write_text(_make_windows_state_storage_json(["/myproject"]))

        result = _get_vscode_projects(storage)
        assert "/myproject" in result

    def test_returns_paths_from_legacy_format(self, tmp_path):
        storage = tmp_path / "storage.json"
        storage.write_text(_make_legacy_storage_json(["/myproject"]))

        result = _get_vscode_projects(storage)
        assert "/myproject" in result

    def test_returns_all_paths_including_nonexistent(self, tmp_path):
        # Remote paths (SSH, WSL, etc.) can't be validated, so we don't check existence
        storage = tmp_path / "storage.json"
        storage.write_text(_make_windows_state_storage_json(["/does/not/exist"]))

        result = _get_vscode_projects(storage)
        assert "/does/not/exist" in result

    def test_returns_empty_on_invalid_json(self, tmp_path):
        storage = tmp_path / "storage.json"
        storage.write_text("not json")
        assert _get_vscode_projects(storage) == []

    def test_returns_empty_on_empty_windows_state(self, tmp_path):
        storage = tmp_path / "storage.json"
        storage.write_text(json.dumps({"windowsState": {}}))
        assert _get_vscode_projects(storage) == []

    def test_multiple_windows(self, tmp_path):
        storage = tmp_path / "storage.json"
        storage.write_text(_make_windows_state_storage_json(["/project1", "/project2"]))

        result = _get_vscode_projects(storage)
        assert "/project1" in result
        assert "/project2" in result


# ---------------------------------------------------------------------------
# VSCodeAdapter
# ---------------------------------------------------------------------------

class TestVSCodeAdapter:
    def setup_method(self):
        self.adapter = VSCodeAdapter()

    def test_name(self):
        assert self.adapter.name == "vscode"

    def test_is_available_when_running(self):
        # VS Code is considered available if the process is running
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)  # pgrep finds Code process
            assert self.adapter.is_available() is True

    def test_is_available_when_cli_present(self):
        # Fallback: CLI exists even if process isn't running
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1)  # pgrep returns 1 (not running)
            with patch("shutil.which", return_value="/usr/local/bin/code"):
                assert self.adapter.is_available() is True

    def test_is_available_when_not_running_and_no_cli(self):
        # Neither running nor CLI present
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1)  # pgrep returns 1
            with patch("shutil.which", return_value=None):
                assert self.adapter.is_available() is False

    def test_get_open_projects_reads_storage(self, tmp_path):
        project_dir = tmp_path / "myproject"
        project_dir.mkdir()
        storage = tmp_path / "storage.json"
        storage.write_text(_make_windows_state_storage_json([str(project_dir)]))

        # Mock AppleScript to return nothing, so it falls back to storage
        with patch("loadout.adapters.ide.vscode._get_projects_from_applescript", return_value=[]):
            with patch("loadout.adapters.ide.vscode._STORAGE_CANDIDATES", [storage]):
                result = self.adapter.get_open_projects()
        assert str(project_dir) in result

    def test_get_open_projects_returns_empty_when_no_storage(self, tmp_path):
        missing = tmp_path / "missing.json"
        with patch("loadout.adapters.ide.vscode._get_projects_from_applescript", return_value=[]):
            with patch("loadout.adapters.ide.vscode._STORAGE_CANDIDATES", [missing]):
                assert self.adapter.get_open_projects() == []

    def test_get_open_projects_prefers_applescript(self, tmp_path):
        """AppleScript results should be used when available."""
        project_dir = tmp_path / "myproject"
        project_dir.mkdir()
        
        with patch("loadout.adapters.ide.vscode._get_projects_from_applescript", return_value=[str(project_dir)]):
            result = self.adapter.get_open_projects()
        assert str(project_dir) in result

    def test_open_project_success(self):
        with patch("subprocess.run", return_value=_make_completed_process(0)) as mock_run:
            result = self.adapter.open_project("/path/to/project")
        assert result is True
        args = mock_run.call_args[0][0]
        assert "code" in args
        assert "/path/to/project" in args

    def test_open_project_failure(self):
        with patch("subprocess.run", return_value=_make_completed_process(1)):
            assert self.adapter.open_project("/path/to/project") is False


# ---------------------------------------------------------------------------
# CursorAdapter
# ---------------------------------------------------------------------------

class TestCursorAdapter:
    def setup_method(self):
        self.adapter = CursorAdapter()

    def test_name(self):
        assert self.adapter.name == "cursor"

    def test_is_available_when_binary_present(self):
        with patch("shutil.which", return_value="/usr/local/bin/cursor"):
            assert self.adapter.is_available() is True

    def test_is_available_when_binary_missing(self):
        with patch("shutil.which", return_value=None):
            assert self.adapter.is_available() is False

    def test_get_open_projects_reads_storage(self, tmp_path):
        project_dir = tmp_path / "cursorproject"
        project_dir.mkdir()
        storage = tmp_path / "storage.json"
        storage.write_text(_make_windows_state_storage_json([str(project_dir)]))

        with patch("loadout.adapters.ide.cursor._get_projects_from_applescript", return_value=[]):
            with patch("loadout.adapters.ide.cursor._STORAGE_PATH", storage):
                result = self.adapter.get_open_projects()
        assert str(project_dir) in result

    def test_get_open_projects_returns_empty_when_no_storage(self, tmp_path):
        missing = tmp_path / "missing.json"
        with patch("loadout.adapters.ide.cursor._get_projects_from_applescript", return_value=[]):
            with patch("loadout.adapters.ide.cursor._STORAGE_PATH", missing):
                assert self.adapter.get_open_projects() == []

    def test_open_project_success(self):
        with patch("subprocess.run", return_value=_make_completed_process(0)) as mock_run:
            result = self.adapter.open_project("/path/to/project")
        assert result is True
        args = mock_run.call_args[0][0]
        assert "cursor" in args

    def test_open_project_failure(self):
        with patch("subprocess.run", return_value=_make_completed_process(1)):
            assert self.adapter.open_project("/path/to/project") is False


# ---------------------------------------------------------------------------
# ZedAdapter
# ---------------------------------------------------------------------------

class TestZedAdapter:
    def setup_method(self):
        self.adapter = ZedAdapter()

    def test_name(self):
        assert self.adapter.name == "zed"

    def test_is_available_when_binary_present(self):
        with patch("shutil.which", return_value="/usr/local/bin/zed"):
            assert self.adapter.is_available() is True

    def test_is_available_when_binary_missing(self):
        with patch("shutil.which", return_value=None):
            assert self.adapter.is_available() is False

    def test_get_open_projects_reads_recent_projects(self, tmp_path):
        project_dir = tmp_path / "zedproject"
        project_dir.mkdir()
        recent = tmp_path / "recent_projects.json"
        recent.write_text(json.dumps([{"paths": [str(project_dir)]}]))

        with patch("loadout.adapters.ide.zed._RECENT_PROJECTS_PATH", recent):
            result = self.adapter.get_open_projects()
        assert str(project_dir) in result

    def test_get_open_projects_skips_nonexistent(self, tmp_path):
        recent = tmp_path / "recent_projects.json"
        recent.write_text(json.dumps([{"paths": ["/does/not/exist"]}]))

        with patch("loadout.adapters.ide.zed._RECENT_PROJECTS_PATH", recent):
            result = self.adapter.get_open_projects()
        assert result == []

    def test_get_open_projects_returns_empty_when_no_file(self, tmp_path):
        missing = tmp_path / "missing.json"
        with patch("loadout.adapters.ide.zed._RECENT_PROJECTS_PATH", missing):
            assert self.adapter.get_open_projects() == []

    def test_get_open_projects_returns_empty_on_invalid_json(self, tmp_path):
        recent = tmp_path / "recent_projects.json"
        recent.write_text("bad json")
        with patch("loadout.adapters.ide.zed._RECENT_PROJECTS_PATH", recent):
            assert self.adapter.get_open_projects() == []

    def test_open_project_success(self):
        with patch("subprocess.run", return_value=_make_completed_process(0)) as mock_run:
            result = self.adapter.open_project("/path/to/project")
        assert result is True
        args = mock_run.call_args[0][0]
        assert "zed" in args

    def test_open_project_failure(self):
        with patch("subprocess.run", return_value=_make_completed_process(1)):
            assert self.adapter.open_project("/path/to/project") is False


# ---------------------------------------------------------------------------
# IDEAdapterRegistry
# ---------------------------------------------------------------------------

class TestIDEAdapterRegistry:
    def test_available_adapters_filters_by_availability(self):
        registry = IDEAdapterRegistry()
        mock_vscode = MagicMock()
        mock_vscode.is_available.return_value = True
        mock_cursor = MagicMock()
        mock_cursor.is_available.return_value = False
        mock_zed = MagicMock()
        mock_zed.is_available.return_value = False
        registry._adapters = [mock_vscode, mock_cursor, mock_zed]

        assert registry.available_adapters() == [mock_vscode]

    def test_available_adapters_empty_when_none_available(self):
        registry = IDEAdapterRegistry()
        # Mock subprocess.run (for pgrep) and shutil.which for all adapters
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1)  # All pgrep calls fail
            with patch("shutil.which", return_value=None):
                assert registry.available_adapters() == []

    def test_get_adapter_vscode(self):
        registry = IDEAdapterRegistry()
        assert registry.get_adapter("vscode").name == "vscode"

    def test_get_adapter_cursor(self):
        registry = IDEAdapterRegistry()
        assert registry.get_adapter("cursor").name == "cursor"

    def test_get_adapter_zed(self):
        registry = IDEAdapterRegistry()
        assert registry.get_adapter("zed").name == "zed"

    def test_get_adapter_unknown_returns_none(self):
        registry = IDEAdapterRegistry()
        assert registry.get_adapter("vim") is None


# ---------------------------------------------------------------------------
# ProjectSet dataclass
# ---------------------------------------------------------------------------

class TestProjectSet:
    def test_default_paths_empty(self):
        ps = ProjectSet(client="vscode")
        assert ps.paths == []

    def test_with_paths(self):
        ps = ProjectSet(client="zed", paths=["/a", "/b"])
        assert len(ps.paths) == 2
