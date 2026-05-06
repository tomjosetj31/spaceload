# Spec-Driven Documentation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Write 7 descriptive markdown spec docs that document existing spaceload behavior so new contributors can orient themselves without reading source code.

**Architecture:** One entry-point overview doc (`docs/ARCHITECTURE.md`) plus six focused subsystem specs in `docs/specs/`. Each doc is written by reading the relevant source files and transcribing behavior into plain prose and tables — no code changes involved.

**Tech Stack:** Markdown, existing Python source as reference material.

---

## File Map

| File to create | Source files to read |
|---|---|
| `docs/ARCHITECTURE.md` | `README.md`, `pyproject.toml`, all subsystem `__init__.py` files |
| `docs/specs/action-schema.md` | `spaceload/daemon/server.py`, `spaceload/replayer/replayer.py` |
| `docs/specs/adapter-contracts.md` | `spaceload/adapters/*/base.py`, `spaceload/adapters/*/registry.py` |
| `docs/specs/daemon.md` | `spaceload/daemon/server.py`, `spaceload/cli/main.py` |
| `docs/specs/replayer.md` | `spaceload/replayer/replayer.py` |
| `docs/specs/store.md` | `spaceload/store/workspace_store.py`, `spaceload/share/exporter.py`, `spaceload/share/sanitizer.py`, `spaceload/share/token_resolver.py` |
| `docs/specs/cli.md` | `spaceload/cli/main.py`, `spaceload/shell/hooks.py` |

---

## Task 1: `docs/ARCHITECTURE.md` — System Overview

**Files:**
- Create: `docs/ARCHITECTURE.md`

- [ ] **Step 1: Write `docs/ARCHITECTURE.md`**

```markdown
# Spaceload — Architecture Overview

Spaceload is a macOS CLI tool that records your developer workspace (browser tabs,
VPN connections, IDE projects, terminal sessions) and replays the entire setup
with a single command. Everything runs locally — no external services involved.

## Data Flow

```
spaceload record <name>
       │
       ▼
  CLI (cli/main.py)
  └─ spawns daemon subprocess
       │
       ▼
  Daemon (daemon/server.py)              ← Unix socket at ~/.spaceload/daemon.sock
  ├─ BrowserPoller  (polls every 2 s)
  ├─ IDEPoller      (polls every 5 s)
  ├─ TerminalPoller (polls every 5 s)
  ├─ VPNPoller      (polls every 2 s)
  └─ WindowSnapshotPoller (polls every 2 s)
       │ accumulates actions in memory
       ▼
spaceload stop  →  daemon flushes actions to Store
                         │
                         ▼
                   Store (store/workspace_store.py)
                   └─ SQLite at ~/.spaceload/spaceload.db

spaceload run <name>
       │
       ▼
  CLI → Store (fetch actions) → Replayer (replayer/replayer.py)
  └─ drives macOS automation (AppleScript, open, subprocess) to reopen everything
```

## Module Map

| Path | Responsibility |
|------|----------------|
| `spaceload/cli/` | Click-based CLI entry point. Routes commands to daemon, store, replayer, and snapshot. |
| `spaceload/daemon/` | Unix socket server. Spawned as a detached subprocess by `record`. Runs pollers in background threads and accumulates actions in memory until `stop`. |
| `spaceload/adapters/browser/` | Per-browser adapters (Chrome, Safari, Arc, Firefox). Read open tabs via AppleScript; open URLs during replay. |
| `spaceload/adapters/vpn/` | Per-VPN-client adapters (Tailscale, WireGuard, Cisco, Mullvad, OpenVPN, Tunnelblick). Detect connection state; connect/disconnect during replay. |
| `spaceload/adapters/ide/` | Per-IDE adapters (VS Code, Cursor, Zed). Read open projects; open project paths during replay. |
| `spaceload/adapters/terminal/` | Per-terminal adapters (iTerm2, Terminal.app, Warp, Kitty). Read open sessions; open directories during replay. |
| `spaceload/adapters/wm/` | Window manager adapters (AeroSpace, yabai). Read which app is in which workspace; move windows during replay. |
| `spaceload/snapshot/` | Synchronous point-in-time capture of the full environment. Used by `spaceload snapshot` (no daemon). |
| `spaceload/store/` | SQLite persistence. Stores workspaces and their action lists. Exports/imports YAML. |
| `spaceload/replayer/` | Walks the action list and drives macOS to reopen each recorded item. |
| `spaceload/diff/` | Compares two action lists and formats a human-readable diff. |
| `spaceload/share/` | Generates portable `.spaceload.yaml` files with path tokens for sharing across machines. |
| `spaceload/shell/` | Generates zsh/bash hook scripts for tracking terminal commands during recording. |
| `spaceload/tui/` | ANSI terminal UI shown during `spaceload record` — live event feed and summary panel. |

## Spec Docs

For deeper reading on each subsystem:

- [`specs/action-schema.md`](specs/action-schema.md) — every action type and its fields
- [`specs/adapter-contracts.md`](specs/adapter-contracts.md) — what each adapter category must implement
- [`specs/daemon.md`](specs/daemon.md) — recording lifecycle, socket protocol, poller behavior
- [`specs/replayer.md`](specs/replayer.md) — replay strategy and session consolidation
- [`specs/store.md`](specs/store.md) — SQLite schema and YAML export/import format
- [`specs/cli.md`](specs/cli.md) — every command, flags, and expected output
```

- [ ] **Step 2: Verify against source**

Check that the module map matches the actual directory listing:
```bash
ls spaceload/
```
Expected directories: `adapters`, `cli`, `daemon`, `diff`, `replayer`, `share`, `shell`, `snapshot`, `store`, `tui`.
Confirm all 11 rows in the module map have a matching directory.

- [ ] **Step 3: Commit**

```bash
git add docs/ARCHITECTURE.md
git commit -m "docs: add ARCHITECTURE.md system overview"
```

---

## Task 2: `docs/specs/action-schema.md` — Action Type Reference

**Files:**
- Create: `docs/specs/action-schema.md`
- Read first: `spaceload/daemon/server.py` (what each poller emits), `spaceload/replayer/replayer.py` (what each handler reads)

- [ ] **Step 1: Write `docs/specs/action-schema.md`**

```markdown
# Action Schema

Actions are the unit of data that flows from the daemon (recording) to the store
(persistence) to the replayer (replay). Each action is a plain dict serialised to
JSON. All actions share two common fields, then carry type-specific fields.

## Common Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `type` | string | yes | Action discriminator. One of the values below. |
| `timestamp` | string (ISO 8601) | yes | UTC time the action was recorded, e.g. `2026-05-06T14:32:00+00:00`. |

---

## `browser_tab_open`

Emitted by `BrowserPoller` when a new tab URL stabilises in a browser (open for
≥ 3 seconds, not a new-tab page, not an internal browser URL).

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `browser` | string | yes | Adapter name: `chrome`, `safari`, `arc`, or `firefox`. |
| `url` | string | yes | Full URL of the opened tab. |
| `workspace` | string | no | AeroSpace workspace label where the browser window lives (e.g. `"1"`). Only present when AeroSpace is running. |

**Example:**
```json
{
  "type": "browser_tab_open",
  "timestamp": "2026-05-06T14:32:00+00:00",
  "browser": "chrome",
  "url": "https://github.com/tomjosetj31/spaceload",
  "workspace": "2"
}
```

---

## `vpn_connect`

Emitted by `VPNPoller` when a VPN transitions from disconnected → connected.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `client` | string | yes | VPN adapter name: `tailscale`, `wireguard`, `cisco`, `mullvad`, `openvpn`, or `tunnelblick`. |
| `profile` | string | no | Connection profile or network name, if the adapter can detect it. |

**Example:**
```json
{
  "type": "vpn_connect",
  "timestamp": "2026-05-06T14:30:00+00:00",
  "client": "tailscale",
  "profile": "my-network"
}
```

---

## `vpn_disconnect`

Emitted by `VPNPoller` when a VPN transitions from connected → disconnected.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `client` | string | yes | VPN adapter name (same values as `vpn_connect`). |

**Example:**
```json
{
  "type": "vpn_disconnect",
  "timestamp": "2026-05-06T14:45:00+00:00",
  "client": "tailscale"
}
```

---

## `ide_project_open`

Emitted by `IDEPoller` when a new project path appears in an IDE.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `client` | string | yes | IDE adapter name: `vscode`, `cursor`, or `zed`. |
| `path` | string | yes | Absolute filesystem path of the opened project/folder. |
| `workspace` | string | no | AeroSpace workspace label. Only present when AeroSpace is running. |

**Example:**
```json
{
  "type": "ide_project_open",
  "timestamp": "2026-05-06T14:31:00+00:00",
  "client": "vscode",
  "path": "/Users/tom/projects/spaceload",
  "workspace": "3"
}
```

---

## `terminal_session_open`

Emitted by `TerminalPoller` when a new terminal session (tab or window) appears.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `app` | string | yes | Terminal adapter name: `iterm2`, `terminal`, `warp`, or `kitty`. |
| `directory` | string | yes | Working directory of the new session. |
| `session_id` | string | no | Unique identifier for the session (typically the tty path, e.g. `/dev/ttys004`). Used by the replayer to consolidate dir-changes and commands. |
| `workspace` | string | no | AeroSpace workspace label. Only present when AeroSpace is running. |

**Example:**
```json
{
  "type": "terminal_session_open",
  "timestamp": "2026-05-06T14:33:00+00:00",
  "app": "iterm2",
  "directory": "/Users/tom/projects/spaceload",
  "session_id": "/dev/ttys004",
  "workspace": "1"
}
```

---

## `terminal_dir_change`

Emitted by `TerminalPoller` when an existing session changes its working directory.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `app` | string | yes | Terminal adapter name. |
| `directory` | string | yes | New working directory. |
| `previous_directory` | string | yes | Directory before the change. |
| `session_id` | string | no | Session identifier (same tty path as in `terminal_session_open`). |

**Example:**
```json
{
  "type": "terminal_dir_change",
  "timestamp": "2026-05-06T14:34:00+00:00",
  "app": "iterm2",
  "directory": "/Users/tom/projects/spaceload/docs",
  "previous_directory": "/Users/tom/projects/spaceload",
  "session_id": "/dev/ttys004"
}
```

---

## `terminal_command`

Emitted by the **shell hook** (not the TerminalPoller) when a command is typed
in a shell with the hook installed. The hook sends this via the Unix socket.
Not emitted automatically — requires `eval "$(spaceload shell-hook zsh)"` in
`~/.zshrc`.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `app` | string | yes | Always `"shell"` (the hook does not know which terminal app is in use). |
| `cmd` | string | yes | The full command string as typed. |
| `directory` | string | yes | Working directory when the command was run. |
| `session_id` | string | yes | tty path, used to associate the command with a `terminal_session_open`. |

**Replay note:** Commands are **displayed but not auto-executed** during replay.
The replayer prints them for reference; the user must run them manually.

**Example:**
```json
{
  "type": "terminal_command",
  "timestamp": "2026-05-06T14:35:00+00:00",
  "app": "shell",
  "cmd": "pytest -v",
  "directory": "/Users/tom/projects/spaceload",
  "session_id": "/dev/ttys004"
}
```

---

## `app_open`

Emitted by `WindowSnapshotPoller` when any application opens that is not handled
by a more specific poller (i.e. not a browser, IDE, or terminal).

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `app_name` | string | yes | macOS application name as reported by the system (e.g. `"Slack"`, `"Spotify"`). |
| `workspace` | string | no | AeroSpace workspace label. Present only when AeroSpace/yabai is running. |

**Example:**
```json
{
  "type": "app_open",
  "timestamp": "2026-05-06T14:36:00+00:00",
  "app_name": "Slack",
  "workspace": "4"
}
```
```

- [ ] **Step 2: Cross-check field names against source**

Open `spaceload/daemon/server.py` and verify every `action["field"]` assignment
matches the field names in this doc. Open `spaceload/replayer/replayer.py` and
verify every `action.get("field")` call matches too.

- [ ] **Step 3: Commit**

```bash
git add docs/specs/action-schema.md
git commit -m "docs: add action-schema spec"
```

---

## Task 3: `docs/specs/adapter-contracts.md` — Adapter Interface Reference

**Files:**
- Create: `docs/specs/adapter-contracts.md`
- Read first: `spaceload/adapters/browser/base.py`, `spaceload/adapters/vpn/base.py`, `spaceload/adapters/ide/base.py`, `spaceload/adapters/terminal/base.py`, `spaceload/adapters/wm/base.py`, and each `registry.py`

- [ ] **Step 1: Write `docs/specs/adapter-contracts.md`**

```markdown
# Adapter Contracts

Spaceload uses a plugin-style adapter system. Each integration category (browser,
VPN, IDE, terminal, window manager) defines an abstract base class. Concrete
adapters subclass it. A registry discovers which adapters are available at runtime
by calling `is_available()` on each.

---

## How Registries Work

Every category has a registry class (e.g. `BrowserAdapterRegistry`). The registry:
1. Instantiates all known adapters at construction time.
2. Exposes `available_adapters()` → returns only those where `is_available()` is True.
3. Exposes `get_adapter(name)` → returns the adapter matching that name, or None.

The daemon's pollers call `available_adapters()` on each poll cycle. The replayer
calls `get_adapter(name)` to find the right adapter for a recorded action.

---

## Browser Adapter (`BrowserAdapter`)

**Base class:** `spaceload/adapters/browser/base.py`
**Implementations:** `chrome.py`, `safari.py`, `arc.py`, `firefox.py`
**Registry:** `spaceload/adapters/browser/registry.py`

| Method | Signature | What it must do |
|--------|-----------|-----------------|
| `name` | `@property → str` | Return a unique lowercase identifier, e.g. `"chrome"`. Used as the `browser` field in `browser_tab_open` actions. |
| `is_available()` | `() → bool` | Return True if this browser is currently running (not just installed). |
| `get_open_tabs()` | `() → list[str]` | Return the full URLs of all currently open tabs. Return `[]` if none or on error. |
| `open_url(url)` | `(str) → bool` | Open the given URL in this browser. Return True on success, False on failure. |

**Minimal stub:**
```python
from spaceload.adapters.browser.base import BrowserAdapter

class MyBrowserAdapter(BrowserAdapter):
    @property
    def name(self) -> str:
        return "mybrowser"

    def is_available(self) -> bool:
        # Check if the app process is running
        ...

    def get_open_tabs(self) -> list[str]:
        # Return list of open tab URLs via AppleScript or other mechanism
        ...

    def open_url(self, url: str) -> bool:
        # Open the URL; return True on success
        ...
```

Register by adding an instance to the `_adapters` list in `BrowserAdapterRegistry.__init__`.

---

## VPN Adapter (`VPNAdapter`)

**Base class:** `spaceload/adapters/vpn/base.py`
**Implementations:** `tailscale.py`, `wireguard.py`, `cisco.py`, `mullvad.py`, `openvpn.py`, `tunnelblick.py`
**Registry:** `spaceload/adapters/vpn/registry.py`

| Method | Signature | What it must do |
|--------|-----------|-----------------|
| `name` | class attribute `str` | Unique lowercase identifier, e.g. `"tailscale"`. Matches the `client` field in VPN actions. |
| `is_available()` | `() → bool` | Return True if the VPN client binary exists on PATH. |
| `detect()` | `() → VPNState \| None` | Return a `VPNState(connected, profile, client)` if the client is installed/running, else None. |
| `connect(config)` | `(dict) → bool` | Connect using the given config dict (the full action dict). Return True on success. |
| `disconnect()` | `() → bool` | Disconnect. Return True on success. |
| `get_config()` | `() → dict` | Return a dict snapshot of current config for replay use. |

**`VPNState` dataclass** (from `base.py`):
```python
@dataclass
class VPNState:
    connected: bool
    profile: str | None = None
    client: str = ""
```

**Registry note:** `VPNAdapterRegistry.detect_active()` iterates all adapters, calls
`detect()`, and returns the first `(adapter, VPNState)` pair where `state.connected`
is True — or None if no VPN is active.

---

## IDE Adapter (`IDEAdapter`)

**Base class:** `spaceload/adapters/ide/base.py`
**Implementations:** `vscode.py`, `cursor.py`, `zed.py`
**Registry:** `spaceload/adapters/ide/registry.py`

| Method | Signature | What it must do |
|--------|-----------|-----------------|
| `name` | `@property → str` | Unique lowercase identifier, e.g. `"vscode"`. Matches the `client` field in `ide_project_open` actions. |
| `is_available()` | `() → bool` | Return True if the IDE binary is present on PATH. |
| `get_open_projects()` | `() → list[str]` | Return absolute paths of all currently open projects/folders. |
| `open_project(path)` | `(str) → bool` | Open the path in this IDE. Return True on success. |

---

## Terminal Adapter (`TerminalAdapter`)

**Base class:** `spaceload/adapters/terminal/base.py`
**Implementations:** `iterm2.py`, `terminal_app.py`, `warp.py`, `kitty.py`
**Registry:** `spaceload/adapters/terminal/registry.py`

| Method | Signature | What it must do |
|--------|-----------|-----------------|
| `name` | `@property → str` | Unique lowercase identifier, e.g. `"iterm2"`. Matches the `app` field in terminal actions. |
| `is_available()` | `() → bool` | Return True if this terminal app is currently running. |
| `get_open_dirs()` | `() → list[str]` | Return working directories of all open terminal sessions. |
| `get_sessions()` | `() → list[TerminalSession]` | Return sessions with `session_id`. Default implementation wraps `get_open_dirs()` — override for accurate session tracking. |
| `open_in_dir(directory)` | `(str) → bool` | Open a new terminal session in the given directory. Return True on success. |

**`TerminalSession` dataclass** (from `base.py`):
```python
@dataclass
class TerminalSession:
    app: str
    directory: str
    session_id: str = ""  # e.g. tty path "/dev/ttys004"
```

**Optional method:** `open_with_commands(directory, commands)` — opens a terminal in
`directory` and sends each command in `commands` to the session. Used by the replayer
when consolidating terminal actions. Fall back to `open_in_dir` if not implemented.

---

## Window Manager Adapter (`WorkspaceManagerAdapter`)

**Base class:** `spaceload/adapters/wm/base.py`
**Implementations:** `aerospace.py`, `yabai.py`
**Registry:** `spaceload/adapters/wm/registry.py`

Used optionally — only when a supported tiling WM is running. Enables workspace
placement during replay.

| Method | Signature | What it must do |
|--------|-----------|-----------------|
| `name` | `@property → str` | Unique lowercase identifier, e.g. `"aerospace"`. |
| `is_available()` | `() → bool` | Return True if the WM binary is on PATH and the WM is running. |
| `list_windows()` | `() → list[WMWindow]` | Return all managed windows with their current workspace assignment. |
| `move_window_to_workspace(window_id, workspace)` | `(int, str) → bool` | Move the given window to the given workspace. Return True on success. |

**`WMWindow` dataclass** (from `base.py`):
```python
@dataclass
class WMWindow:
    window_id: int
    workspace: str   # workspace label as a string, e.g. "1", "browser"
    app_name: str    # macOS app name, e.g. "Google Chrome"
```

**Convenience methods** (implemented on the base class, no need to override):
- `get_app_workspace(app_name)` → workspace of first window belonging to the app
- `get_app_window_ids(app_name)` → list of window IDs for the app
- `move_app_to_workspace(app_name, workspace)` → moves the app's first window
```

- [ ] **Step 2: Verify method signatures against source**

For each base class, confirm every method name and signature in the doc matches
what is in the source file. Run a quick grep:
```bash
grep -n "def " spaceload/adapters/browser/base.py spaceload/adapters/vpn/base.py \
  spaceload/adapters/ide/base.py spaceload/adapters/terminal/base.py \
  spaceload/adapters/wm/base.py
```

- [ ] **Step 3: Commit**

```bash
git add docs/specs/adapter-contracts.md
git commit -m "docs: add adapter-contracts spec"
```

---

## Task 4: `docs/specs/daemon.md` — Recording Daemon

**Files:**
- Create: `docs/specs/daemon.md`
- Read first: `spaceload/daemon/server.py`, `spaceload/cli/main.py` (the `record` command)

- [ ] **Step 1: Write `docs/specs/daemon.md`**

```markdown
# Daemon Spec

The recording daemon is a separate Python process that runs in the background
during a `spaceload record` session. It owns the Unix socket, runs all poller
threads, and accumulates actions in memory until `spaceload stop` is called.

---

## Recording Lifecycle

```
spaceload record <name>
    │
    ├─ checks no daemon is already running (PID file + socket both must be absent)
    ├─ spawns daemon: python -m spaceload.daemon.server <name> --db <path> [--include-open]
    ├─ waits up to 2 s for ~/.spaceload/daemon.sock to appear
    └─ starts the TUI (or prints plain text if --no-tui or not a TTY)

daemon starts
    │
    ├─ creates workspace row in SQLite
    ├─ writes PID to ~/.spaceload/daemon.pid
    ├─ creates Unix socket at ~/.spaceload/daemon.sock
    ├─ starts 5 poller threads (VPN, Browser, IDE, Terminal, WindowSnapshot)
    └─ enters accept() loop (1 s timeout, checks self._running each cycle)

spaceload stop  (or Ctrl+C in TUI)
    │
    ├─ sends {"command": "stop"} to socket
    ├─ daemon flushes all accumulated actions to SQLite
    ├─ daemon removes socket file and PID file
    └─ daemon process exits
```

---

## File Locations

| File | Purpose |
|------|---------|
| `~/.spaceload/daemon.sock` | Unix domain socket. Presence indicates an active recording session. |
| `~/.spaceload/daemon.pid` | PID of the daemon process. |
| `~/.spaceload/daemon.log` | Structured log of all poller activity during recording. |
| `~/.spaceload/spaceload.db` | SQLite database (default path). |

---

## Unix Socket Protocol

All messages are newline-terminated JSON. The daemon reads until it sees `\n`,
then responds with a newline-terminated JSON object.

### `record_action` — record a single action

**Request:**
```json
{"command": "record_action", "action": { ...action dict... }}
```
**Response:**
```json
{"status": "ok"}
```
Used by the shell hook to send `terminal_command` actions.

### `stop` — flush and shut down

**Request:**
```json
{"command": "stop"}
```
**Response:**
```json
{"status": "ok", "workspace": "<name>", "action_count": 42}
```

### `status` — query action count

**Request:**
```json
{"command": "status"}
```
**Response:**
```json
{"status": "ok", "workspace": "<name>", "action_count": 7}
```

### `events` — fetch actions since an offset

**Request:**
```json
{"command": "events", "since": 0}
```
**Response:**
```json
{"status": "ok", "events": [...actions...], "total": 42}
```
The TUI uses this to poll for new events during recording. `since` is the
last-seen action count; the response returns only actions from that index onward.

---

## Pollers

All pollers share the same pattern: they run in a daemon thread, poll at a fixed
interval, and append action dicts to the shared `_actions` list. The list is
read under Python's GIL — no explicit locking needed for append + slice.

### `VPNPoller`

- **Interval:** 2 seconds
- **How it works:** calls `VPNAdapterRegistry.detect_active()` each cycle. On
  the first poll it records the baseline state without emitting an action. On
  subsequent polls it emits `vpn_connect` when transitioning disconnected→connected
  and `vpn_disconnect` when transitioning connected→disconnected.

### `BrowserPoller`

- **Interval:** 2 seconds
- **How it works:** calls `get_open_tabs()` on each available browser adapter.
  First poll per browser sets the baseline (no events). New URLs go into a
  *pending* dict. A URL is recorded only after it has been continuously open
  for ≥ 3 seconds (stabilisation), preventing redirect chains. A per-domain
  cooldown of 5 seconds prevents duplicate events for the same domain.
- **`--include-open`:** If set, the baseline poll records all currently open
  tabs immediately instead of using them as a silent baseline.

### `IDEPoller`

- **Interval:** 5 seconds
- **How it works:** calls `get_open_projects()` on each available IDE adapter.
  First poll sets baseline. New paths → `ide_project_open` events.
- **`--include-open`:** records all projects open at start.

### `TerminalPoller`

- **Interval:** 5 seconds
- **How it works:** calls `get_sessions()` on each available terminal adapter.
  Tracks sessions by `session_id`. New `session_id` → `terminal_session_open`.
  Changed `directory` for a known `session_id` → `terminal_dir_change`.
  Falls back to `get_open_dirs()` for adapters that do not implement `get_sessions()`.
- **`--include-open`:** records all open sessions at start.

### `WindowSnapshotPoller`

- **Interval:** 2 seconds
- **WM mode:** if AeroSpace or yabai is running, uses `list_windows()` to detect
  new windows by `window_id`. Records `app_open` for any new window whose app is
  not already handled by a richer poller (browsers, IDEs, terminals).
- **Fallback mode:** polls running foreground apps via AppleScript
  (`System Events`) and records `app_open` for newly appeared app names.
- **`--include-open`:** records all open apps at start.
```

- [ ] **Step 2: Verify socket message shapes against source**

Check that every request/response shape matches what `_handle_connection` in
`spaceload/daemon/server.py` actually reads and writes:
```bash
grep -n '"command"' spaceload/daemon/server.py
```
Confirm `record_action`, `stop`, `status`, `events` are all handled.

- [ ] **Step 3: Commit**

```bash
git add docs/specs/daemon.md
git commit -m "docs: add daemon spec"
```

---

## Task 5: `docs/specs/replayer.md` — Replay Strategy

**Files:**
- Create: `docs/specs/replayer.md`
- Read first: `spaceload/replayer/replayer.py`

- [ ] **Step 1: Write `docs/specs/replayer.md`**

```markdown
# Replayer Spec

The replayer walks the stored action list in timestamp order and drives macOS
automation to reopen each recorded item. It is invoked by `spaceload run <name>`.

---

## Replay Ordering

Actions are replayed in the order they were recorded (ascending timestamp, as
returned by `WorkspaceStore.get_actions()`). The replayer processes them
sequentially — one action at a time, no parallelism.

---

## Terminal Session Consolidation

The replayer pre-processes terminal-related actions before the main loop via
`_consolidate_terminal_sessions()`:

1. It groups `terminal_command` actions by `session_id`.
2. It maps each `session_id` to its `terminal_session_open` action (which carries
   the start directory and app name).
3. When the main loop encounters a `terminal_session_open`, it calls
   `_handle_terminal_session_consolidated()` instead of the plain handler. This
   opens ONE terminal in the start directory and passes all associated commands
   to `open_with_commands()`.
4. Subsequent `terminal_dir_change` and `terminal_command` actions for the same
   `session_id` are skipped — they have already been handled.

**Why:** Without consolidation, the replayer would open a new terminal window for
every directory change, producing many redundant windows.

---

## Per-Action Replay Strategy

### `vpn_connect`
1. Look up the VPN adapter by `client` name.
2. Call `adapter.connect(action)` with the full action dict as config.
3. Retry up to 3 times with 2-second delays between attempts.
4. Log a warning and continue on failure (never aborts the replay).

### `vpn_disconnect`
1. Look up adapter by `client` name.
2. Call `adapter.disconnect()`. No retry.
3. Log and continue on failure.

### `browser_tab_open`
1. Look up adapter by `browser` name.
2. Call `adapter.open_url(url)`.
3. If no adapter found, fall back to `open <url>` (system default browser).
4. If `workspace` field is present and AeroSpace is running, move the browser
   window to that workspace after opening.

### `ide_project_open`
1. Look up adapter by `client` name.
2. Call `adapter.open_project(path)`.
3. Log and continue if no adapter or if open fails.
4. AeroSpace workspace placement if `workspace` field present.

### `terminal_session_open`
- If `session_id` is in the consolidated sessions map → `_handle_terminal_session_consolidated()`:
  calls `adapter.open_with_commands(start_directory, commands)` if available,
  otherwise falls back to `adapter.open_in_dir(start_directory)`.
- If `session_id` is not in the map → `_handle_terminal_session_open()`: calls
  `adapter.open_in_dir(directory)`.

### `terminal_dir_change`
- If the session was already handled by consolidation → skip.
- Otherwise → open a new terminal in `directory` (the replayer cannot change
  directory in an existing remote session).

### `terminal_command`
- If the session was handled by consolidation → skip.
- Otherwise → **display the command and directory** to stdout. Commands are
  never auto-executed for safety.

### `app_open`
1. Call `open -a <app_name>` via subprocess.
2. AeroSpace workspace placement if `workspace` field present.

---

## AeroSpace Workspace Placement

After opening any app (browser, IDE, terminal, generic), if the recorded action
has a `workspace` field and AeroSpace is running, the replayer:

1. Waits 1.5 seconds for the window to appear (`_AEROSPACE_SETTLE`).
2. Calls `aerospace.move_app_to_workspace(app_os_name, workspace)`.

For terminal sessions, it captures window IDs before and after opening to move
only the newly created window.

---

## Error Handling

All handlers catch failures and continue. The replayer never aborts mid-replay:
- Missing adapter → log warning, print `[warn]`, skip action.
- Subprocess failure → log warning, print `[warn]`, continue.
- VPN failure → retry 3× then continue.

A detailed replay log is written to `~/.spaceload/replay.log`.
```

- [ ] **Step 2: Verify consolidation logic against source**

Confirm `_consolidate_terminal_sessions` in `spaceload/replayer/replayer.py`
matches what the doc says — specifically that it uses `session_id` as the
grouping key and filters out `spaceload ` / `ctx ` commands:
```bash
grep -n "consolidate\|session_id\|ctx " spaceload/replayer/replayer.py
```

- [ ] **Step 3: Commit**

```bash
git add docs/specs/replayer.md
git commit -m "docs: add replayer spec"
```

---

## Task 6: `docs/specs/store.md` — Persistence Layer

**Files:**
- Create: `docs/specs/store.md`
- Read first: `spaceload/store/workspace_store.py`, `spaceload/share/exporter.py`, `spaceload/share/sanitizer.py`, `spaceload/share/token_resolver.py`

- [ ] **Step 1: Write `docs/specs/store.md`**

```markdown
# Store Spec

Spaceload persists workspaces and their actions in a SQLite database at
`~/.spaceload/spaceload.db`. It also supports two YAML formats: a native
export format and a portable share format.

---

## SQLite Schema

```sql
CREATE TABLE workspaces (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    name         TEXT UNIQUE NOT NULL,
    created_at   TEXT NOT NULL,        -- ISO 8601 UTC timestamp
    last_run     TEXT,                 -- ISO 8601 UTC timestamp, NULL if never run
    action_count INTEGER DEFAULT 0
);

CREATE TABLE actions (
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
in the file. Some tokens are resolved automatically (e.g. `{{HOME}}` → current
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
```

- [ ] **Step 2: Verify schema against source**

Confirm the SQL schema in the doc exactly matches `_SCHEMA_SQL` in
`spaceload/store/workspace_store.py`:
```bash
grep -A 20 "_SCHEMA_SQL" spaceload/store/workspace_store.py
```

- [ ] **Step 3: Commit**

```bash
git add docs/specs/store.md
git commit -m "docs: add store spec"
```

---

## Task 7: `docs/specs/cli.md` — Command Reference

**Files:**
- Create: `docs/specs/cli.md`
- Read first: `spaceload/cli/main.py`, `spaceload/shell/hooks.py`

- [ ] **Step 1: Write `docs/specs/cli.md`**

```markdown
# CLI Spec

All commands are accessed via the `spaceload` binary. Run `spaceload --help`
or `spaceload <command> --help` for built-in help text.

---

## `spaceload record <name>`

Start recording a workspace session.

**Arguments:** `name` — the workspace name to record under (required).

**Flags:**

| Flag | Default | Description |
|------|---------|-------------|
| `--include-open` / `-i` | off | Also capture apps, tabs, and projects already open when recording starts. By default only new items opened after `record` is run are captured. |
| `--no-tui` | off | Disable the live TUI panel; print plain text instead. Useful in CI or when stdout is not a TTY. |

**Side effects:**
- Spawns a detached daemon subprocess (`python -m spaceload.daemon.server`).
- Creates `~/.spaceload/daemon.sock` and `~/.spaceload/daemon.pid`.
- If a TUI is shown (default when stdout is a TTY), blocks until the user presses Ctrl+C or `spaceload stop` is called externally.

**Exit codes:** 1 if a recording session is already active.

**Example:**
```
$ spaceload record my-project
Recording 'my-project' — press Ctrl+C to stop
  [1] browser_tab_open: chrome → https://github.com/...
  [2] ide_project_open: vscode → /Users/tom/projects/my-project
```

---

## `spaceload stop`

Stop the active recording session and save it to the store.

**Side effects:**
- Sends `{"command": "stop"}` to the daemon socket.
- Daemon flushes all accumulated actions to SQLite, then exits.
- Removes `~/.spaceload/daemon.sock` and `~/.spaceload/daemon.pid`.

**Exit codes:** 1 if no recording session is active, or if the daemon returns an error.

**Example:**
```
$ spaceload stop
Saved 12 actions for 'my-project'
```

---

## `spaceload run <name>`

Replay a saved workspace.

**Arguments:** `name` — workspace name to replay (required).

**Side effects:** Drives macOS automation (AppleScript, `open`, subprocess) to
reopen each recorded item. Writes a detailed log to `~/.spaceload/replay.log`.

**Exit codes:** 1 if the workspace is not found.

**Example:**
```
$ spaceload run my-project
[ctx] Replaying workspace 'my-project' (12 actions)
    [1] browser_tab_open: browser='chrome' url='https://github.com/...'
         [ok] Opened in chrome
    [2] ide_project_open: client='vscode' path='/Users/tom/projects/my-project'
         [ok] Opened /Users/tom/projects/... in vscode
```

---

## `spaceload list`

List all saved workspaces.

**Example output:**
```
Name          Actions                   Created  Last Run
--------------------------------------------------------------------------
my-project         12  2026-05-06T14:30:00+00:00  2026-05-06T18:00:00+00:00
other-project       5  2026-05-01T10:00:00+00:00  never
```

---

## `spaceload show <name>`

Print the native YAML export of a workspace to stdout.

**Arguments:** `name` — workspace name (required).

**Exit codes:** 1 if workspace not found.

---

## `spaceload delete <name>`

Delete a saved workspace and all its actions.

**Arguments:** `name` — workspace name (required).

**Flags:**

| Flag | Description |
|------|-------------|
| `--yes` / `-y` | Skip the confirmation prompt. |

**Exit codes:** 1 if workspace not found.

---

## `spaceload snapshot <name>`

Instantly capture the current environment as a workspace — no daemon required.

**Arguments:** `name` — workspace name to save under (required).

**Flags:**

| Flag | Description |
|------|-------------|
| `--overwrite` | Replace an existing workspace with the same name. Without this flag, exits with an error if the name is taken. |
| `--description` / `-d` | Optional description tag embedded in the workspace name. |

**Side effects:** Reads all open browsers, IDEs, terminals, and VPN state synchronously (takes ~1–2 s). Saves directly to SQLite.

**Example:**
```
$ spaceload snapshot quick-save
Capturing current environment…

Snapshot saved: quick-save
  Browser tabs:  3 (chrome)
  IDE:           vscode → /Users/tom/projects/spaceload
  Terminals:     2 session(s)
```

---

## `spaceload diff <name-a> [name-b]`

Show a visual diff between a saved workspace and the current environment, or between two saved workspaces.

**Arguments:** `name-a` — first workspace (required). `name-b` — second workspace (optional).

**Flags:**

| Flag | Description |
|------|-------------|
| `--current` | Compare `name-a` against the current live environment. This is the default when only one name is given. |

**Examples:**
```bash
spaceload diff my-project              # my-project vs current environment
spaceload diff workspace-a workspace-b  # two saved workspaces
```

---

## `spaceload share <name>`

Export a workspace as a portable `.spaceload.yaml` file. Absolute paths are
replaced with token placeholders (`{{PROJECT_ROOT}}`, `{{HOME}}`).

**Arguments:** `name` — workspace name (required).

**Flags:**

| Flag | Description |
|------|-------------|
| `--output` / `-o <path>` | Write to a specific file path instead of `<name>.spaceload.yaml`. |
| `--clipboard` | Copy the YAML to the macOS clipboard (`pbcopy`). |
| `--description` / `-d <text>` | Embed a human-readable description in the share file. |
| `--print` | Print YAML to stdout instead of writing a file. |

**Default output:** `<name>.spaceload.yaml` in the current directory.

---

## `spaceload import [file]`

Import a workspace from a YAML file (or stdin).

Supports both the native `spaceload show` format and the portable
`.spaceload.yaml` share format. For share files, token placeholders are
resolved automatically where possible; the user is prompted for any
unknown tokens.

**Arguments:** `file` — path to YAML file (optional; reads stdin if omitted).

---

## `spaceload shell-hook <shell>`

Print the shell integration script for command tracking to stdout.

**Arguments:** `shell` — one of `zsh` or `bash` (required).

**Usage:**
```bash
# Add to ~/.zshrc:
eval "$(spaceload shell-hook zsh)"

# Add to ~/.bashrc:
eval "$(spaceload shell-hook bash)"
```

The hook uses `preexec` (zsh) or the `DEBUG` trap (bash) to send each command
to the daemon socket as a `terminal_command` action. Commands are only sent
when a recording session is active (the hook checks for the socket before
each command). No overhead when not recording.
```

- [ ] **Step 2: Verify commands against source**

Confirm every `@cli.command(...)` in `spaceload/cli/main.py` has a matching
section in the doc:
```bash
grep "@cli.command" spaceload/cli/main.py
```
Expected: `record`, `stop`, `run`, `delete`, `list`, `share`, `import`,
`show`, `snapshot`, `diff`, `shell-hook`.

- [ ] **Step 3: Commit**

```bash
git add docs/specs/cli.md
git commit -m "docs: add cli spec"
```

---

## Task 8: Final verification and index commit

- [ ] **Step 1: Check all files exist**

```bash
ls docs/ docs/specs/
```
Expected output:
```
docs/:
ARCHITECTURE.md  specs/  superpowers/

docs/specs/:
action-schema.md  adapter-contracts.md  cli.md  daemon.md  replayer.md  store.md
```

- [ ] **Step 2: Verify all spec links in ARCHITECTURE.md resolve**

The links in `ARCHITECTURE.md` use relative paths like `specs/action-schema.md`.
Confirm each file exists by checking the listing above.

- [ ] **Step 3: Final commit**

```bash
git add docs/
git commit -m "docs: complete spec-driven documentation set"
```
