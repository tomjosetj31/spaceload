# ctx — Workspace Context Switcher

A macOS CLI tool that records and replays developer workspace setups: browser tabs, VPN connections, IDE projects, and terminal sessions.

## Overview

`ctx` lets you snapshot your entire development environment and restore it later with a single command. Stop context-switching overhead and get back into flow faster.

## Features

- **Record** workspace sessions (browser tabs, VPN, IDE, terminals)
- **Replay** saved workspaces in one command
- **Export/Import** workspace definitions as YAML
- **List** and manage saved workspaces

## Installation

```bash
git clone https://github.com/tomjosetj31/ctx
cd ctx
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

## Usage

```bash
# Start recording a workspace session
ctx record my-project

# ... open your browser tabs, connect VPN, open IDE, etc. ...

# Stop recording and save the session
ctx stop

# Replay a saved workspace
ctx run my-project

# List all saved workspaces
ctx list

# Inspect a workspace as YAML
ctx show my-project

# Delete a workspace
ctx delete my-project

# Import a workspace from a YAML file
ctx import my-project.yaml
```

### Recording Options

```bash
# Record only new things opened during recording (default)
ctx record my-project

# Also capture everything already open when recording starts
ctx record my-project --include-open
# or
ctx record my-project -i
```

## Supported Integrations

### Specialized Adapters (Rich Tracking)

These apps have dedicated adapters that track specific details:

| Category | Supported | What's Tracked |
|----------|-----------|----------------|
| **Browser** | Chrome, Safari, Arc, Firefox | Individual tab URLs |
| **VPN** | Tailscale, WireGuard, Cisco AnyConnect, Mullvad, OpenVPN, Tunnelblick | Connection state & profile |
| **IDE** | VS Code, Cursor, Zed | Open project/folder paths |
| **Terminal** | iTerm2, Terminal.app, Warp, Kitty | Working directories per session, commands (with shell hook) |

### Generic App Tracking

Any **other application** you open during recording is automatically tracked as an `app_open` action with the app name. This includes apps like Notes, Calendar, Slack, Spotify, etc.

### Firefox Support

Firefox tab reading requires the `lz4` library to parse session files:

```bash
# Install with Firefox support
pip install -e ".[firefox]"

# Or install lz4 separately
pip install lz4
```

Without `lz4`, Firefox tabs won't be read during recording, but URLs can still be opened during replay.

### Terminal Command Tracking

To track terminal commands during recording, add the shell hook to your shell config:

```bash
# For zsh (~/.zshrc):
eval "$(ctx shell-hook zsh)"

# For bash (~/.bashrc):
eval "$(ctx shell-hook bash)"
```

Then restart your shell or run `source ~/.zshrc`.

**How it works:**
- Commands are only tracked when a recording session is active
- The hook checks for the daemon socket before sending (no overhead when not recording)
- Commands run in the background so they don't slow down your shell
- During replay, commands are **displayed but not auto-executed** (for safety)

### Smart Browser Filtering

The recorder automatically filters out:
- **New tab pages** (`chrome://newtab/`, `about:newtab`, etc.)
- **Internal browser pages** (`chrome://`, `about:`, `safari-resource:`, etc.)
- **Intermediate URLs** (pages open less than 3 seconds)
- **Redirect chains** (multiple URLs from same domain in quick succession)

## Logs & Debugging

Logs are written to `~/.ctx/` for debugging:

```bash
# Daemon log (recording)
cat ~/.ctx/daemon.log

# Replay log
cat ~/.ctx/replay.log
```

## Architecture

- **CLI** (`ctx/cli/`) — Click-based command interface
- **Daemon** (`ctx/daemon/`) — Unix socket server that records actions in the background
- **Store** (`ctx/store/`) — SQLite-backed persistence layer with YAML export/import
- **Replayer** (`ctx/replayer/`) — Replays recorded action sequences
- **Adapters** (`ctx/adapters/`) — Per-integration plugins (browser, VPN, IDE, terminal)

## Tech Stack

- Python 3.11+
- [Click](https://click.palletsprojects.com/) for the CLI
- SQLite (stdlib) for persistence
- PyYAML for export/import
- Unix domain sockets for CLI↔daemon IPC

## License

MIT — see [LICENSE](LICENSE).
