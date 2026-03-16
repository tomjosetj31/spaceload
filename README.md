# Spaceload — Workspace Context Switcher

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](CONTRIBUTING.md)

A macOS CLI tool that records and replays developer workspace setups: browser tabs, VPN connections, IDE projects, and terminal sessions.

## Overview

`spaceload` lets you snapshot your entire development environment and restore it later with a single command. Stop context-switching overhead and get back into flow faster.

## Features

- **Record** workspace sessions (browser tabs, VPN, IDE, terminals)
- **Replay** saved workspaces in one command
- **Export/Import** workspace definitions as YAML
- **List** and manage saved workspaces

## Installation

**Via pip:**
```bash
pip install spaceload
```

**Via Homebrew:**
```bash
brew tap tomjosetj31/spaceload
brew install tomjosetj31/spaceload/spaceload
```

**From source:**
```bash
git clone https://github.com/tomjosetj31/spaceload
cd spaceload
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

## Usage

```bash
# Start recording a workspace session
spaceload record my-project

# ... open your browser tabs, connect VPN, open IDE, etc. ...

# Stop recording and save the session
spaceload stop

# Replay a saved workspace
spaceload run my-project

# List all saved workspaces
spaceload list

# Inspect a workspace as YAML
spaceload show my-project

# Delete a workspace
spaceload delete my-project

# Import a workspace from a YAML file
spaceload import my-project.yaml
```

### Recording Options

```bash
# Record only new things opened during recording (default)
spaceload record my-project

# Also capture everything already open when recording starts
spaceload record my-project --include-open
# or
spaceload record my-project -i
```

## Privacy & Permissions

**Spaceload runs entirely on your machine. It never sends any data to a server, the internet, or any external service.** Everything is stored locally in `~/.spaceload/`.

macOS will prompt you to grant the following permissions the first time they are needed:

| Permission | Why it's needed |
|------------|-----------------|
| **Automation** | Used to control browsers (Chrome, Safari, Arc), IDEs (VS Code, Cursor), terminals (iTerm2, Terminal.app, Warp), and Tunnelblick via AppleScript to read open tabs, project paths, and connection state. macOS will show a dialog for each app the first time. |
| **Accessibility** | Used via `System Events` to list running processes and read window titles (e.g. to detect which IDE projects are open). |
| **Full Disk Access** | Required to read Firefox's session files (`~/Library/Application Support/Firefox/`) and VS Code/Cursor workspace state (`~/Library/Application Support/Code/` or `Cursor/`). Without this, those adapters fall back to window-title heuristics. |

You can review and revoke these at any time in **System Settings → Privacy & Security**.

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
eval "$(spaceload shell-hook zsh)"

# For bash (~/.bashrc):
eval "$(spaceload shell-hook bash)"
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

Logs are written to `~/.spaceload/` for debugging:

```bash
# Daemon log (recording)
cat ~/.spaceload/daemon.log

# Replay log
cat ~/.spaceload/replay.log
```

## Architecture

- **CLI** (`spaceload/cli/`) — Click-based command interface
- **Daemon** (`spaceload/daemon/`) — Unix socket server that records actions in the background
- **Store** (`spaceload/store/`) — SQLite-backed persistence layer with YAML export/import
- **Replayer** (`spaceload/replayer/`) — Replays recorded action sequences
- **Adapters** (`spaceload/adapters/`) — Per-integration plugins (browser, VPN, IDE, terminal)

## Tech Stack

- Python 3.11+
- [Click](https://click.palletsprojects.com/) for the CLI
- SQLite (stdlib) for persistence
- PyYAML for export/import
- Unix domain sockets for CLI↔daemon IPC

## Contributing

Contributions are welcome! Whether it's a bug fix, a new adapter for an app you use, or a documentation improvement — all PRs are appreciated.

Please read [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines on how to set up the project locally, run tests, and submit a pull request.

## License

MIT — see [LICENSE](LICENSE).
