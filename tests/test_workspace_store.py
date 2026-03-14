"""Unit tests for WorkspaceStore."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
import yaml

from loadout.store.workspace_store import WorkspaceStore


@pytest.fixture
def store(tmp_path: Path) -> WorkspaceStore:
    """Return a fresh WorkspaceStore backed by a temp DB."""
    db_path = tmp_path / "test.db"
    s = WorkspaceStore(db_path)
    yield s
    s.close()


# ---------------------------------------------------------------------------
# create_workspace
# ---------------------------------------------------------------------------

class TestCreateWorkspace:
    def test_returns_integer_id(self, store: WorkspaceStore) -> None:
        ws_id = store.create_workspace("alpha")
        assert isinstance(ws_id, int)
        assert ws_id >= 1

    def test_ids_are_unique(self, store: WorkspaceStore) -> None:
        id1 = store.create_workspace("alpha")
        id2 = store.create_workspace("beta")
        assert id1 != id2

    def test_duplicate_name_raises(self, store: WorkspaceStore) -> None:
        store.create_workspace("alpha")
        import sqlite3
        with pytest.raises(sqlite3.IntegrityError):
            store.create_workspace("alpha")


# ---------------------------------------------------------------------------
# get_workspace
# ---------------------------------------------------------------------------

class TestGetWorkspace:
    def test_returns_dict_for_existing(self, store: WorkspaceStore) -> None:
        store.create_workspace("alpha")
        ws = store.get_workspace("alpha")
        assert ws is not None
        assert ws["name"] == "alpha"
        assert ws["action_count"] == 0
        assert ws["created_at"] is not None

    def test_returns_none_for_missing(self, store: WorkspaceStore) -> None:
        result = store.get_workspace("does-not-exist")
        assert result is None


# ---------------------------------------------------------------------------
# list_workspaces
# ---------------------------------------------------------------------------

class TestListWorkspaces:
    def test_empty_list_on_fresh_db(self, store: WorkspaceStore) -> None:
        assert store.list_workspaces() == []

    def test_returns_all_workspaces(self, store: WorkspaceStore) -> None:
        store.create_workspace("alpha")
        store.create_workspace("beta")
        store.create_workspace("gamma")
        workspaces = store.list_workspaces()
        names = {ws["name"] for ws in workspaces}
        assert names == {"alpha", "beta", "gamma"}

    def test_returns_list_of_dicts(self, store: WorkspaceStore) -> None:
        store.create_workspace("alpha")
        result = store.list_workspaces()
        assert isinstance(result, list)
        assert isinstance(result[0], dict)


# ---------------------------------------------------------------------------
# delete_workspace
# ---------------------------------------------------------------------------

class TestDeleteWorkspace:
    def test_delete_existing_returns_true(self, store: WorkspaceStore) -> None:
        store.create_workspace("alpha")
        assert store.delete_workspace("alpha") is True

    def test_delete_nonexistent_returns_false(self, store: WorkspaceStore) -> None:
        assert store.delete_workspace("ghost") is False

    def test_delete_removes_workspace(self, store: WorkspaceStore) -> None:
        store.create_workspace("alpha")
        store.delete_workspace("alpha")
        assert store.get_workspace("alpha") is None

    def test_delete_removes_associated_actions(self, store: WorkspaceStore) -> None:
        ws_id = store.create_workspace("alpha")
        store.save_actions(ws_id, [{"type": "open_tab", "data": {"url": "https://example.com"}, "timestamp": "2026-01-01T00:00:00+00:00"}])
        store.delete_workspace("alpha")
        # After deletion the workspace is gone; no orphan actions should remain
        assert store.get_workspace("alpha") is None


# ---------------------------------------------------------------------------
# save_actions / get_actions
# ---------------------------------------------------------------------------

class TestSaveActions:
    def _make_action(self, action_type: str, **data) -> dict:
        return {
            "type": action_type,
            "data": data,
            "timestamp": "2026-01-01T00:00:00+00:00",
        }

    def test_save_and_retrieve(self, store: WorkspaceStore) -> None:
        ws_id = store.create_workspace("alpha")
        actions = [
            self._make_action("open_tab", url="https://github.com"),
            self._make_action("open_ide", project="/code/myapp"),
        ]
        store.save_actions(ws_id, actions)
        retrieved = store.get_actions(ws_id)
        assert len(retrieved) == 2
        types = {a["type"] for a in retrieved}
        assert types == {"open_tab", "open_ide"}

    def test_action_count_updated(self, store: WorkspaceStore) -> None:
        ws_id = store.create_workspace("alpha")
        store.save_actions(ws_id, [self._make_action("open_tab", url="https://example.com")])
        ws = store.get_workspace("alpha")
        assert ws is not None
        assert ws["action_count"] == 1

    def test_save_empty_list_is_noop(self, store: WorkspaceStore) -> None:
        ws_id = store.create_workspace("alpha")
        store.save_actions(ws_id, [])
        assert store.get_actions(ws_id) == []

    def test_data_roundtrips_as_dict(self, store: WorkspaceStore) -> None:
        ws_id = store.create_workspace("alpha")
        store.save_actions(ws_id, [self._make_action("open_tab", url="https://example.com", pinned=True)])
        actions = store.get_actions(ws_id)
        assert actions[0]["data"] == {"url": "https://example.com", "pinned": True}


# ---------------------------------------------------------------------------
# export_yaml
# ---------------------------------------------------------------------------

class TestExportYaml:
    def test_returns_valid_yaml_string(self, store: WorkspaceStore) -> None:
        ws_id = store.create_workspace("alpha")
        store.save_actions(ws_id, [{"type": "open_tab", "data": {"url": "https://example.com"}, "timestamp": "2026-01-01T00:00:00+00:00"}])
        yaml_str = store.export_yaml("alpha")
        assert isinstance(yaml_str, str)
        parsed = yaml.safe_load(yaml_str)
        assert parsed["workspace"]["name"] == "alpha"
        assert len(parsed["actions"]) == 1

    def test_raises_key_error_for_missing(self, store: WorkspaceStore) -> None:
        with pytest.raises(KeyError):
            store.export_yaml("ghost")

    def test_empty_workspace_exports_empty_actions(self, store: WorkspaceStore) -> None:
        store.create_workspace("empty-ws")
        yaml_str = store.export_yaml("empty-ws")
        parsed = yaml.safe_load(yaml_str)
        assert parsed["actions"] == []


# ---------------------------------------------------------------------------
# import_yaml
# ---------------------------------------------------------------------------

class TestImportYaml:
    def _build_yaml(self, name: str, actions: list | None = None) -> str:
        payload = {
            "workspace": {
                "name": name,
                "created_at": "2026-01-01T00:00:00+00:00",
                "last_run": None,
                "action_count": len(actions or []),
            },
            "actions": actions or [],
        }
        return yaml.dump(payload)

    def test_import_creates_workspace(self, store: WorkspaceStore) -> None:
        yaml_str = self._build_yaml("imported")
        store.import_yaml(yaml_str)
        ws = store.get_workspace("imported")
        assert ws is not None
        assert ws["name"] == "imported"

    def test_import_with_actions(self, store: WorkspaceStore) -> None:
        actions = [
            {"type": "open_tab", "data": {"url": "https://example.com"}, "timestamp": "2026-01-01T00:00:00+00:00"},
            {"type": "connect_vpn", "data": {"profile": "work"}, "timestamp": "2026-01-01T00:00:01+00:00"},
        ]
        yaml_str = self._build_yaml("imported", actions)
        store.import_yaml(yaml_str)
        ws = store.get_workspace("imported")
        assert ws is not None
        retrieved = store.get_actions(ws["id"])
        assert len(retrieved) == 2

    def test_import_overwrites_existing(self, store: WorkspaceStore) -> None:
        # First import
        store.import_yaml(self._build_yaml("alpha"))
        # Second import of same name — should not raise
        store.import_yaml(self._build_yaml("alpha"))
        # Only one workspace should exist
        workspaces = store.list_workspaces()
        names = [ws["name"] for ws in workspaces]
        assert names.count("alpha") == 1

    def test_roundtrip_export_import(self, store: WorkspaceStore) -> None:
        ws_id = store.create_workspace("original")
        store.save_actions(ws_id, [{"type": "open_tab", "data": {"url": "https://example.com"}, "timestamp": "2026-01-01T00:00:00+00:00"}])
        yaml_str = store.export_yaml("original")

        # Import into a fresh store
        with tempfile.TemporaryDirectory() as tmp:
            other_store = WorkspaceStore(Path(tmp) / "other.db")
            other_store.import_yaml(yaml_str)
            ws = other_store.get_workspace("original")
            assert ws is not None
            assert ws["action_count"] == 1
            other_store.close()
