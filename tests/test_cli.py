"""CLI tests using Click's test runner."""

from __future__ import annotations

import io
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml

from click.testing import CliRunner

from loadout.cli.main import cli
from loadout.store.workspace_store import WorkspaceStore


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def store(tmp_path):
    """Return a WorkspaceStore backed by a temp DB."""
    db_path = tmp_path / "test.db"
    s = WorkspaceStore(db_path)
    yield s
    s.close()


@pytest.fixture
def patched_store(tmp_path):
    """Patch _get_store to return a temp store, yield (runner, store)."""
    db_path = tmp_path / "test.db"

    def _make_store():
        return WorkspaceStore(db_path)

    runner = CliRunner()
    with patch("loadout.cli.main._get_store", side_effect=_make_store):
        yield runner, db_path


# ---------------------------------------------------------------------------
# ctx run
# ---------------------------------------------------------------------------

class TestRunCommand:
    def test_run_not_found(self, patched_store):
        runner, db_path = patched_store
        result = runner.invoke(cli, ["run", "nonexistent"])
        assert result.exit_code == 1
        assert "not found" in result.output.lower() or "not found" in (result.stderr or "").lower()

    def test_run_replays_workspace(self, patched_store):
        runner, db_path = patched_store

        # Create a workspace in the DB
        store = WorkspaceStore(db_path)
        ws_id = store.create_workspace("myworkspace")
        store.save_actions(ws_id, [
            {
                "type": "browser_tab_open",
                "browser": "chrome",
                "url": "https://example.com",
                "timestamp": "2026-01-01T00:00:00+00:00",
            }
        ])
        store.close()

        with patch("loadout.replayer.replayer.Replayer.replay") as mock_replay:
            result = runner.invoke(cli, ["run", "myworkspace"])

        assert result.exit_code == 0
        mock_replay.assert_called_once()


# ---------------------------------------------------------------------------
# ctx delete
# ---------------------------------------------------------------------------

class TestDeleteCommand:
    def test_delete_workspace(self, patched_store):
        runner, db_path = patched_store

        # Create workspace first
        store = WorkspaceStore(db_path)
        store.create_workspace("to-delete")
        store.close()

        result = runner.invoke(cli, ["delete", "--yes", "to-delete"])
        assert result.exit_code == 0
        assert "deleted" in result.output.lower()

        # Verify it's gone
        store = WorkspaceStore(db_path)
        assert store.get_workspace("to-delete") is None
        store.close()

    def test_delete_nonexistent(self, patched_store):
        runner, db_path = patched_store
        result = runner.invoke(cli, ["delete", "--yes", "nonexistent"])
        assert result.exit_code == 1

    def test_delete_prompts_without_yes_flag(self, patched_store):
        runner, db_path = patched_store

        # Create workspace first
        store = WorkspaceStore(db_path)
        store.create_workspace("to-delete")
        store.close()

        # Answer "n" to the prompt — should abort
        result = runner.invoke(cli, ["delete", "to-delete"], input="n\n")
        assert result.exit_code != 0

    def test_delete_with_yes_prompt_confirmed(self, patched_store):
        runner, db_path = patched_store

        # Create workspace first
        store = WorkspaceStore(db_path)
        store.create_workspace("to-delete")
        store.close()

        # Answer "y" to the prompt
        result = runner.invoke(cli, ["delete", "to-delete"], input="y\n")
        assert result.exit_code == 0
        assert "deleted" in result.output.lower()


# ---------------------------------------------------------------------------
# ctx import
# ---------------------------------------------------------------------------

class TestImportCommand:
    def _make_yaml(self, name: str = "imported") -> str:
        payload = {
            "workspace": {
                "name": name,
                "created_at": "2026-01-01T00:00:00+00:00",
                "last_run": None,
                "action_count": 1,
            },
            "actions": [
                {
                    "type": "browser_tab_open",
                    "browser": "chrome",
                    "url": "https://example.com",
                    "timestamp": "2026-01-01T00:00:00+00:00",
                }
            ],
        }
        return yaml.dump(payload, default_flow_style=False)

    def test_import_workspace_from_file(self, patched_store, tmp_path):
        runner, db_path = patched_store

        yaml_file = tmp_path / "workspace.yaml"
        yaml_file.write_text(self._make_yaml("file-imported"))

        result = runner.invoke(cli, ["import", str(yaml_file)])
        assert result.exit_code == 0
        assert "imported" in result.output.lower()

        store = WorkspaceStore(db_path)
        ws = store.get_workspace("file-imported")
        store.close()
        assert ws is not None

    def test_import_stdin(self, patched_store):
        runner, db_path = patched_store
        yaml_str = self._make_yaml("stdin-imported")

        result = runner.invoke(cli, ["import"], input=yaml_str)
        assert result.exit_code == 0
        assert "imported" in result.output.lower()

        store = WorkspaceStore(db_path)
        ws = store.get_workspace("stdin-imported")
        store.close()
        assert ws is not None


# ---------------------------------------------------------------------------
# ctx list
# ---------------------------------------------------------------------------

class TestListCommand:
    def test_list_empty(self, patched_store):
        runner, db_path = patched_store
        result = runner.invoke(cli, ["list"])
        assert result.exit_code == 0
        assert "no workspaces" in result.output.lower()

    def test_list_with_workspaces(self, patched_store):
        runner, db_path = patched_store

        store = WorkspaceStore(db_path)
        store.create_workspace("alpha")
        store.create_workspace("beta")
        store.close()

        result = runner.invoke(cli, ["list"])
        assert result.exit_code == 0
        assert "alpha" in result.output
        assert "beta" in result.output


# ---------------------------------------------------------------------------
# ctx show
# ---------------------------------------------------------------------------

class TestShowCommand:
    def test_show_workspace(self, patched_store):
        runner, db_path = patched_store

        store = WorkspaceStore(db_path)
        ws_id = store.create_workspace("myws")
        store.save_actions(ws_id, [
            {
                "type": "browser_tab_open",
                "browser": "chrome",
                "url": "https://example.com",
                "timestamp": "2026-01-01T00:00:00+00:00",
            }
        ])
        store.close()

        result = runner.invoke(cli, ["show", "myws"])
        assert result.exit_code == 0
        assert "myws" in result.output
        assert "browser_tab_open" in result.output

    def test_show_not_found(self, patched_store):
        runner, db_path = patched_store
        result = runner.invoke(cli, ["show", "nonexistent"])
        assert result.exit_code == 1
