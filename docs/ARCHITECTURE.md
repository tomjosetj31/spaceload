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
| `spaceload/adapters/wm/` | Abstract base class and registry for window manager adapters (AeroSpace, yabai). Read which app is in which workspace; move windows during replay. |
| `spaceload/adapters/aerospace/` | AeroSpace-specific adapter used directly by the daemon and replayer for workspace queries when AeroSpace is the active window manager. |
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
