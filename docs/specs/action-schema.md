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
Not emitted automatically — requires the shell hook to be installed:
`eval "$(spaceload shell-hook zsh)"` in `~/.zshrc` (zsh) or
`eval "$(spaceload shell-hook bash)"` in `~/.bashrc` (bash).

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
| `workspace` | string | no | AeroSpace workspace label. Present only when AeroSpace or yabai is running. |

**Example:**
```json
{
  "type": "app_open",
  "timestamp": "2026-05-06T14:36:00+00:00",
  "app_name": "Slack",
  "workspace": "4"
}
```
