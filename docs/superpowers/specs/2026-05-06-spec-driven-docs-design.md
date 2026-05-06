# Design: Spec-Driven Documentation for Spaceload

**Date:** 2026-05-06
**Status:** Approved
**Type:** Descriptive — documents existing behavior for new contributors

---

## Problem

Spaceload has no `docs/` directory. Key system behaviors are implicit:

- Action types (`browser_tab_open`, `vpn_connect`, etc.) are raw dicts with no canonical schema
- Adapter contracts exist as abstract base classes but are not explained in plain language
- The daemon's socket protocol, polling behavior, and lifecycle are only discoverable by reading 1,177 lines of `daemon/server.py`
- A new contributor adding an adapter has no reference for what to implement or why

The result: the code is the only source of truth, making onboarding slow and adapter authoring error-prone.

---

## Goal

Create a set of formal, descriptive markdown spec documents that describe what the system *already does* — so new contributors can orient themselves by reading docs, not source.

---

## Non-Goals

- Prescriptive/forward-looking specs (future features are not in scope)
- API reference generated from docstrings (this is hand-written prose)
- Changing any code (pure documentation work)

---

## Approach: Per-Subsystem Spec Docs

A `docs/specs/` directory with one focused file per major subsystem, plus a top-level `docs/ARCHITECTURE.md` as the entry point.

### File Layout

```
docs/
├── ARCHITECTURE.md              # Entry point: overview, data flow, module map
└── specs/
    ├── action-schema.md         # Every action type, its fields, and valid values
    ├── adapter-contracts.md     # What each adapter category must implement and why
    ├── daemon.md                # Recording lifecycle, socket protocol, poller behavior
    ├── replayer.md              # Replay ordering, session consolidation, fallback logic
    ├── store.md                 # SQLite schema, YAML export/import format
    └── cli.md                   # Every command, flags, exit codes, expected output
```

---

## Document Designs

### `docs/ARCHITECTURE.md`
- What spaceload does in 2–3 sentences
- Text-based data flow diagram: CLI → Daemon → Pollers → Store → Replayer
- Module map: one line per directory explaining its role
- Links to each spec doc for deeper reading

### `docs/specs/action-schema.md`
The most valuable doc. Defines every action type as a table:

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `type` | string | yes | Action discriminator, e.g. `browser_tab_open` |
| ...   | ...  | ...      | ...         |

Covers: `browser_tab_open`, `vpn_connect`, `vpn_disconnect`, `ide_project_open`,
`terminal_session_open`, `terminal_dir_change`, `terminal_command`, `app_open`.

Each action gets: field table, valid values, example JSON, notes on when it is emitted.

### `docs/specs/adapter-contracts.md`
For each adapter category (browser, VPN, IDE, terminal, window manager):
- The abstract base class and its methods
- What each method must do (plain English, not code)
- What return values mean
- How the registry discovers and selects adapters
- A minimal stub showing the shape of a new adapter

### `docs/specs/daemon.md`
- Recording lifecycle: how `spaceload record` spawns the daemon, how `spaceload stop` shuts it down
- Unix socket protocol: the exact JSON shape of each message (`record_action`, `stop`, `status`, `events`) and responses
- Poller inventory: what each of the five pollers tracks, at what interval, and how it emits actions
- How `include_open` changes baseline behavior

### `docs/specs/replayer.md`
- How actions are fetched from the store and passed to the replayer
- Replay ordering: actions are replayed in recorded order
- Terminal session consolidation: why it exists, how `session_id` groups actions
- Per-action-type replay strategy (VPN retry logic, browser fallback, terminal `open_with_commands`)
- AeroSpace workspace placement: the settle delay and move mechanism
- What "commands are displayed, not executed" means and why

### `docs/specs/store.md`
- SQLite table schema: `workspaces` and `actions` tables, column names and types
- How actions are serialized to JSON in the DB
- YAML export format: the structure of `spaceload show` output
- Share file format (`.spaceload.yaml`): fields, token placeholders, how `spaceload import` resolves them

### `docs/specs/cli.md`
For each command (`record`, `stop`, `run`, `list`, `show`, `delete`, `snapshot`, `diff`, `share`, `import`, `shell-hook`):
- Synopsis
- Arguments and flags with descriptions
- Side effects (what files/processes are created or modified)
- Exit codes
- Example output

---

## What Is Not Documented

- Internal implementation details (algorithm internals, private methods) — the specs cover *behavior*, not *how*
- AppleScript scripts used inside adapters — these are implementation detail
- Test suite structure — covered by `CONTRIBUTING.md`

---

## Success Criteria

A developer unfamiliar with spaceload can:
1. Read `ARCHITECTURE.md` and understand the system in under 5 minutes
2. Find the schema for any action type without reading source code
3. Write a new adapter stub by reading `adapter-contracts.md` alone
4. Understand what the daemon socket protocol accepts without reading `server.py`
