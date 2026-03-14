"""Click CLI root for loadout — Workspace Context Switcher."""

from __future__ import annotations

import json
import socket
import subprocess
import sys
from pathlib import Path

import click

_LOADOUT_DIR = Path.home() / ".loadout"
_SOCKET_PATH = _LOADOUT_DIR / "daemon.sock"
_PID_PATH = _LOADOUT_DIR / "daemon.pid"
_DEFAULT_DB = _LOADOUT_DIR / "loadout.db"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _daemon_is_running() -> bool:
    """Return True if a daemon PID file and socket both exist."""
    return _PID_PATH.exists() and _SOCKET_PATH.exists()


def _send_to_daemon(message: dict) -> dict:
    """Send a JSON message to the daemon and return the parsed response."""
    payload = (json.dumps(message) + "\n").encode()
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        sock.connect(str(_SOCKET_PATH))
        sock.sendall(payload)
        response_data = b""
        while True:
            chunk = sock.recv(4096)
            if not chunk:
                break
            response_data += chunk
            if b"\n" in response_data:
                break
        return json.loads(response_data.decode().strip())
    finally:
        sock.close()


def _get_store():
    """Return a WorkspaceStore pointed at the default DB."""
    from loadout.store.workspace_store import WorkspaceStore
    _LOADOUT_DIR.mkdir(parents=True, exist_ok=True)
    return WorkspaceStore(_DEFAULT_DB)


# ---------------------------------------------------------------------------
# CLI root
# ---------------------------------------------------------------------------

@click.group()
@click.version_option(package_name="loadout")
def cli() -> None:
    """loadout — record and replay developer workspace setups."""


# ---------------------------------------------------------------------------
# loadout record <name>
# ---------------------------------------------------------------------------

@cli.command("record")
@click.argument("name")
@click.option(
    "--include-open", "-i",
    is_flag=True,
    default=False,
    help="Also capture apps/tabs/projects already open when recording starts.",
)
def record(name: str, include_open: bool) -> None:
    """Start recording a workspace session named NAME.
    
    By default, only captures new things opened during recording.
    Use --include-open to also capture everything already open.
    """
    if _daemon_is_running():
        click.echo(
            "A recording session is already active. Run 'loadout stop' first.",
            err=True,
        )
        sys.exit(1)

    _LOADOUT_DIR.mkdir(parents=True, exist_ok=True)

    # Spawn the daemon as a detached subprocess
    daemon_cmd = [
        sys.executable,
        "-m",
        "loadout.daemon.server",
        name,
        "--db",
        str(_DEFAULT_DB),
    ]
    
    if include_open:
        daemon_cmd.append("--include-open")

    proc = subprocess.Popen(
        daemon_cmd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,  # detach from parent's process group
    )

    # Give the daemon a moment to create the socket
    import time
    for _ in range(20):
        if _SOCKET_PATH.exists():
            break
        time.sleep(0.1)
    else:
        click.echo(
            f"Daemon failed to start (pid={proc.pid}). Check logs.",
            err=True,
        )
        sys.exit(1)

    msg = f"Recording started for '{name}'."
    if include_open:
        msg += " (including already open apps)"
    msg += " Run 'loadout stop' when done."
    click.echo(msg)


# ---------------------------------------------------------------------------
# loadout stop
# ---------------------------------------------------------------------------

@cli.command("stop")
def stop() -> None:
    """Stop the active recording session and save it to the store."""
    if not _daemon_is_running():
        click.echo("No active recording session found.", err=True)
        sys.exit(1)

    try:
        response = _send_to_daemon({"command": "stop"})
    except (ConnectionRefusedError, FileNotFoundError, OSError) as exc:
        click.echo(f"Could not reach daemon: {exc}", err=True)
        sys.exit(1)

    if response.get("status") == "ok":
        workspace = response.get("workspace", "?")
        action_count = response.get("action_count", 0)
        click.echo(f"Saved {action_count} actions for '{workspace}'")
    else:
        click.echo(f"Daemon returned an error: {response}", err=True)
        sys.exit(1)


# ---------------------------------------------------------------------------
# loadout run <name>
# ---------------------------------------------------------------------------

@cli.command("run")
@click.argument("name")
def run(name: str) -> None:
    """Replay the saved workspace named NAME."""
    store = _get_store()
    try:
        ws = store.get_workspace(name)
        if ws is None:
            click.echo(f"Workspace '{name}' not found.", err=True)
            sys.exit(1)
        actions = store.get_actions(ws["id"])
        store.mark_last_run(name)
    finally:
        store.close()

    from loadout.replayer.replayer import Replayer
    replayer = Replayer(name, actions)
    replayer.replay()


# ---------------------------------------------------------------------------
# loadout delete <name>
# ---------------------------------------------------------------------------

@cli.command("delete")
@click.argument("name")
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation prompt.")
def delete(name: str, yes: bool) -> None:
    """Delete a saved workspace named NAME."""
    if not yes:
        click.confirm(f"Delete workspace '{name}'?", abort=True)
    store = _get_store()
    try:
        deleted = store.delete_workspace(name)
    finally:
        store.close()
    if not deleted:
        click.echo(f"Workspace '{name}' not found.", err=True)
        sys.exit(1)
    click.echo(f"Deleted workspace '{name}'.")


# ---------------------------------------------------------------------------
# loadout list
# ---------------------------------------------------------------------------

@cli.command("list")
def list_workspaces() -> None:
    """List all saved workspaces."""
    store = _get_store()
    try:
        workspaces = store.list_workspaces()
    finally:
        store.close()

    if not workspaces:
        click.echo("No workspaces saved yet. Use 'loadout record <name>' to start.")
        return

    # Simple table
    col_name = max(len(w["name"]) for w in workspaces)
    col_name = max(col_name, 4)  # min width for "Name"
    header = f"{'Name':<{col_name}}  {'Actions':>7}  {'Created':>24}  Last Run"
    click.echo(header)
    click.echo("-" * len(header))
    for ws in workspaces:
        last_run = ws["last_run"] or "never"
        click.echo(
            f"{ws['name']:<{col_name}}  {ws['action_count']:>7}  "
            f"{ws['created_at']:>24}  {last_run}"
        )


# ---------------------------------------------------------------------------
# loadout import [file]
# ---------------------------------------------------------------------------

@cli.command("import")
@click.argument("file", type=click.Path(exists=True), required=False)
def import_workspace(file: str | None) -> None:
    """Import a workspace from a YAML FILE (or stdin if omitted)."""
    if file:
        yaml_str = Path(file).read_text()
    else:
        if sys.stdin.isatty():
            click.echo("Provide a FILE argument or pipe YAML via stdin.", err=True)
            sys.exit(1)
        yaml_str = sys.stdin.read()
    store = _get_store()
    try:
        store.import_yaml(yaml_str)
    finally:
        store.close()
    click.echo("Workspace imported successfully.")


# ---------------------------------------------------------------------------
# loadout show <name>
# ---------------------------------------------------------------------------

@cli.command("show")
@click.argument("name")
def show(name: str) -> None:
    """Print the YAML export of workspace NAME."""
    store = _get_store()
    try:
        try:
            yaml_str = store.export_yaml(name)
        except KeyError as exc:
            click.echo(str(exc), err=True)
            sys.exit(1)
    finally:
        store.close()

    click.echo(yaml_str, nl=False)


# ---------------------------------------------------------------------------
# loadout shell-hook <shell>
# ---------------------------------------------------------------------------

@cli.command("shell-hook")
@click.argument("shell", type=click.Choice(["zsh", "bash"], case_sensitive=False))
def shell_hook(shell: str) -> None:
    """Output shell integration script for command tracking.
    
    Add to your shell config:
    
    \b
    # For zsh (~/.zshrc):
    eval "$(ctx shell-hook zsh)"
    
    \b
    # For bash (~/.bashrc):
    eval "$(ctx shell-hook bash)"
    
    This enables tracking of terminal commands during recording sessions.
    Commands are only sent when a recording session is active.
    """
    from loadout.shell.hooks import get_hook_script
    click.echo(get_hook_script(shell))
