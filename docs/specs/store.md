# Store Spec

Spaceload persists workspaces and their actions in a SQLite database at
`~/.spaceload/spaceload.db`. It also supports two YAML formats: a native
export format and a portable share format.

---

## SQLite Schema

```sql
CREATE TABLE IF NOT EXISTS workspaces (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    name         TEXT UNIQUE NOT NULL,
    created_at   TEXT NOT NULL,        -- ISO 8601 UTC timestamp
    last_run     TEXT,                 -- ISO 8601 UTC timestamp, NULL if never run
    action_count INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS actions (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    workspace_id INTEGER NOT NULL,
    type         TEXT NOT NULL,        -- action type discriminator, e.g. "browser_tab_open"
    data         TEXT NOT NULL,        -- JSON blob of all fields except "type" and "timestamp"
    timestamp    TEXT NOT NULL,        -- ISO 8601 UTC timestamp
    FOREIGN KEY (workspace_id) REFERENCES workspaces(id)
);
```

**How actions are stored:** The `type` and `timestamp` fields are lifted to
top-level columns. All other fields are stored together in the `data` JSON blob.
When actions are read back via `get_actions()`, `type` and `timestamp` are merged
back into the dict along with the parsed `data` fields.

---

## Native YAML Export Format

Produced by `spaceload show <name>` / `WorkspaceStore.export_yaml()`.
Suitable for backup and re-import on the same machine.

```yaml
workspace:
  name: my-project
  created_at: "2026-05-06T14:30:00+00:00"
  last_run: "2026-05-06T18:00:00+00:00"
  action_count: 12

actions:
  - type: browser_tab_open
    timestamp: "2026-05-06T14:32:00+00:00"
    browser: chrome
    url: https://github.com/tomjosetj31/spaceload
  - type: vpn_connect
    timestamp: "2026-05-06T14:30:00+00:00"
    client: tailscale
    profile: my-network
  # ... one entry per action
```

Import with `spaceload import <file.yaml>`.

---

## Share File Format (`.spaceload.yaml`)

Produced by `spaceload share <name>`. Designed to be portable across machines.
Absolute paths are replaced with token placeholders like `{{PROJECT_ROOT}}` and
`{{HOME}}`.

```yaml
spaceload:
  version: 1
  share_id: a1b2c3d4          # 8-character random hex ID
  created_at: "2026-05-06T14:30:00Z"
  platform: macOS
  description: "Optional description"  # only if --description was passed

workspace:
  name: my-project
  project_root: "{{PROJECT_ROOT}}"   # only present if a project root was detected

browser:
  app: chrome
  tabs:
    - https://github.com/tomjosetj31/spaceload
    - https://docs.python.org

ide:
  app: vscode
  workspace_path: "{{PROJECT_ROOT}}"

terminals:
  - app: iterm2
    cwd: "{{PROJECT_ROOT}}"
    command: pytest -v        # optional, only if a startup command was recorded

vpn:
  vpn: tailscale
```

**Token resolution on import:** `spaceload import` detects `{{TOKEN}}` patterns
in the file. Some tokens are resolved automatically (e.g. `{{HOME}}` -> current
user's home directory). Unknown tokens prompt the user for a local path.

---

## `WorkspaceStore` API

| Method | What it does |
|--------|-------------|
| `create_workspace(name)` | Insert a workspace row; return its integer id. |
| `get_workspace(name)` | Return workspace dict or None. |
| `list_workspaces()` | Return all workspaces ordered by `created_at` DESC. |
| `delete_workspace(name)` | Delete workspace and all its actions. Return True if found. |
| `mark_last_run(name)` | Update `last_run` to now. |
| `save_actions(workspace_id, actions)` | Persist a list of action dicts; increment `action_count`. |
| `get_actions(workspace_id)` | Return all actions ordered by `timestamp` ASC. |
| `export_yaml(name)` | Return native YAML string. Raises `KeyError` if name not found. |
| `import_yaml(yaml_str)` | Parse native YAML and insert. Replaces existing workspace of same name. |
| `close()` | Close the SQLite connection. Also usable as a context manager. |
