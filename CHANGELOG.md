# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2026-03-14

### Added
- Record workspace sessions: browser tabs, VPN connections, IDE projects, and terminal sessions
- Replay saved workspaces with a single command (`loadout run`)
- Export and import workspace definitions as YAML
- Specialized adapters for Chrome, Safari, Arc, and Firefox (browser tabs)
- Specialized adapters for Tailscale, WireGuard, Cisco AnyConnect, Mullvad, OpenVPN, and Tunnelblick (VPN)
- Specialized adapters for VS Code, Cursor, and Zed (IDE)
- Specialized adapters for iTerm2, Terminal.app, Warp, and Kitty (terminal)
- Generic app tracking for any other macOS application opened during recording
- Shell hook support for zsh and bash to track terminal commands during recording
- Smart browser filtering to ignore new tab pages, internal pages, and transient URLs
- `--include-open` / `-i` flag to capture already-open apps at recording start
- SQLite-backed persistence with YAML export/import
- `loadout list`, `loadout show`, `loadout delete`, `loadout import` commands

[0.1.0]: https://github.com/tomjosetj31/loadout/releases/tag/v0.1.0
