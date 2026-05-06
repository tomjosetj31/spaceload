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
