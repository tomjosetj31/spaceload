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
