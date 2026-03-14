"""SQLite-backed persistence layer for ctx workspaces and actions."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml


_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS workspaces (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL,
    created_at TEXT NOT NULL,
    last_run TEXT,
    action_count INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS actions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    workspace_id INTEGER NOT NULL,
    type TEXT NOT NULL,
    data TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    FOREIGN KEY (workspace_id) REFERENCES workspaces(id)
);
"""


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class WorkspaceStore:
    """Manages workspace and action persistence in a SQLite database."""

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._conn.executescript(_SCHEMA_SQL)
        self._conn.commit()

    # ------------------------------------------------------------------
    # Workspace CRUD
    # ------------------------------------------------------------------

    def create_workspace(self, name: str) -> int:
        """Insert a new workspace row and return its id."""
        cursor = self._conn.execute(
            "INSERT INTO workspaces (name, created_at, action_count) VALUES (?, ?, ?)",
            (name, _now_iso(), 0),
        )
        self._conn.commit()
        return cursor.lastrowid  # type: ignore[return-value]

    def get_workspace(self, name: str) -> dict[str, Any] | None:
        """Return workspace dict by name, or None if not found."""
        row = self._conn.execute(
            "SELECT * FROM workspaces WHERE name = ?", (name,)
        ).fetchone()
        return dict(row) if row else None

    def list_workspaces(self) -> list[dict[str, Any]]:
        """Return all workspace rows as a list of dicts."""
        rows = self._conn.execute(
            "SELECT * FROM workspaces ORDER BY created_at DESC"
        ).fetchall()
        return [dict(r) for r in rows]

    def delete_workspace(self, name: str) -> bool:
        """Delete workspace and its actions. Returns True if a row was deleted."""
        ws = self.get_workspace(name)
        if ws is None:
            return False
        self._conn.execute(
            "DELETE FROM actions WHERE workspace_id = ?", (ws["id"],)
        )
        self._conn.execute("DELETE FROM workspaces WHERE name = ?", (name,))
        self._conn.commit()
        return True

    def mark_last_run(self, name: str) -> None:
        """Update last_run timestamp for a workspace."""
        self._conn.execute(
            "UPDATE workspaces SET last_run = ? WHERE name = ?",
            (_now_iso(), name),
        )
        self._conn.commit()

    # ------------------------------------------------------------------
    # Action persistence
    # ------------------------------------------------------------------

    def save_actions(self, workspace_id: int, actions: list[dict[str, Any]]) -> None:
        """Persist a list of action dicts and update the workspace action_count."""
        if not actions:
            return
        rows = [
            (
                workspace_id,
                action.get("type", "unknown"),
                json.dumps({k: v for k, v in action.items() if k not in ("type", "timestamp")}),
                action.get("timestamp", _now_iso()),
            )
            for action in actions
        ]
        self._conn.executemany(
            "INSERT INTO actions (workspace_id, type, data, timestamp) VALUES (?, ?, ?, ?)",
            rows,
        )
        self._conn.execute(
            "UPDATE workspaces SET action_count = action_count + ? WHERE id = ?",
            (len(actions), workspace_id),
        )
        self._conn.commit()

    def get_actions(self, workspace_id: int) -> list[dict[str, Any]]:
        """Return all actions for a workspace ordered by timestamp."""
        rows = self._conn.execute(
            "SELECT * FROM actions WHERE workspace_id = ? ORDER BY timestamp ASC",
            (workspace_id,),
        ).fetchall()
        result = []
        for r in rows:
            d = dict(r)
            action_dict = {
                "id": d["id"],
                "workspace_id": d["workspace_id"],
                "type": d["type"],
                "timestamp": d["timestamp"],
            }
            action_dict.update(json.loads(d["data"]))
            result.append(action_dict)
        return result

    # ------------------------------------------------------------------
    # YAML export / import
    # ------------------------------------------------------------------

    def export_yaml(self, name: str) -> str:
        """Return a YAML string representing the workspace and its actions."""
        ws = self.get_workspace(name)
        if ws is None:
            raise KeyError(f"Workspace '{name}' not found")
        actions = self.get_actions(ws["id"])
        payload = {
            "workspace": {
                "name": ws["name"],
                "created_at": ws["created_at"],
                "last_run": ws["last_run"],
                "action_count": ws["action_count"],
            },
            "actions": [
                {k: v for k, v in a.items() if k not in ("id", "workspace_id")}
                for a in actions
            ],
        }
        return yaml.dump(payload, default_flow_style=False, allow_unicode=True, sort_keys=False)

    def import_yaml(self, yaml_str: str) -> None:
        """Import a workspace and its actions from a YAML string.

        If a workspace with the same name already exists it is deleted first.
        """
        payload = yaml.safe_load(yaml_str)
        ws_data = payload["workspace"]
        name = ws_data["name"]

        # Remove existing workspace with the same name if present
        self.delete_workspace(name)

        # Insert with action_count=0; save_actions will increment it correctly.
        cursor = self._conn.execute(
            "INSERT INTO workspaces (name, created_at, last_run, action_count) VALUES (?, ?, ?, ?)",
            (
                name,
                ws_data.get("created_at", _now_iso()),
                ws_data.get("last_run"),
                0,
            ),
        )
        self._conn.commit()
        workspace_id = cursor.lastrowid

        actions = payload.get("actions", [])
        if actions:
            self.save_actions(workspace_id, actions)

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    def close(self) -> None:
        """Close the underlying database connection."""
        self._conn.close()

    def __enter__(self) -> "WorkspaceStore":
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()
