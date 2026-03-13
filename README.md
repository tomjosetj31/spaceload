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
git clone https://github.com/tom/ctx
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
