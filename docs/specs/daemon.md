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
