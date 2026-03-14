"""Click CLI root for spaceload — Workspace Context Switcher."""

from __future__ import annotations

import json
import socket
import subprocess
import sys
from pathlib import Path

import click

_SPACELOAD_DIR = Path.home() / ".spaceload"
_SOCKET_PATH = _SPACELOAD_DIR / "daemon.sock"
_PID_PATH = _SPACELOAD_DIR / "daemon.pid"
_DEFAULT_DB = _SPACELOAD_DIR / "spaceload.db"


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
    from spaceload.store.workspace_store import WorkspaceStore
    _SPACELOAD_DIR.mkdir(parents=True, exist_ok=True)
    return WorkspaceStore(_DEFAULT_DB)


# ---------------------------------------------------------------------------
# CLI root
# ---------------------------------------------------------------------------

@click.group()
@click.version_option(package_name="spaceload")
def cli() -> None:
    """spaceload — record and replay developer workspace setups."""


# ---------------------------------------------------------------------------
# spaceload record <name>
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
            "A recording session is already active. Run 'spaceload stop' first.",
            err=True,
        )
        sys.exit(1)

    _SPACELOAD_DIR.mkdir(parents=True, exist_ok=True)

    # Spawn the daemon as a detached subprocess
    daemon_cmd = [
        sys.executable,
        "-m",
        "spaceload.daemon.server",
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
    msg += " Run 'spaceload stop' when done."
    click.echo(msg)


# ---------------------------------------------------------------------------
# spaceload stop
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
# spaceload run <name>
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

    from spaceload.replayer.replayer import Replayer
    replayer = Replayer(name, actions)
    replayer.replay()


# ---------------------------------------------------------------------------
# spaceload delete <name>
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
# spaceload list
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
        click.echo("No workspaces saved yet. Use 'spaceload record <name>' to start.")
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
# spaceload share <name>
# ---------------------------------------------------------------------------

@cli.command("share")
@click.argument("name")
@click.option("--output", "-o", type=click.Path(), default=None, help="Write to a specific file path.")
@click.option("--clipboard", is_flag=True, help="Copy YAML to clipboard (macOS pbcopy).")
@click.option("--description", "-d", default=None, help="Human-readable description to embed in the file.")
@click.option("--print", "print_stdout", is_flag=True, help="Print YAML to stdout instead of writing a file.")
def share(name: str, output: str | None, clipboard: bool, description: str | None, print_stdout: bool) -> None:
    """Export workspace NAME as a portable .spaceload.yaml file for sharing."""
    store = _get_store()
    try:
        ws = store.get_workspace(name)
        if ws is None:
            click.echo(f"Workspace '{name}' not found.", err=True)
            sys.exit(1)
        actions = store.get_actions(ws["id"])
    finally:
        store.close()

    from spaceload.share.exporter import generate_share_yaml
    yaml_content = generate_share_yaml(name, actions, description=description)

    if print_stdout:
        click.echo(yaml_content, nl=False)
        return

    if clipboard:
        try:
            subprocess.run(["pbcopy"], input=yaml_content.encode(), check=True)
            click.echo(f"Workspace '{name}' copied to clipboard.")
        except (FileNotFoundError, subprocess.CalledProcessError) as exc:
            click.echo(f"Clipboard copy failed: {exc}", err=True)
            sys.exit(1)
        return

    out_path = Path(output) if output else Path(f"{name}.spaceload.yaml")
    out_path.write_text(yaml_content)
    click.echo(f"Shared: {out_path}")
    click.echo(f"Anyone can import it with: spaceload import {out_path}")


# ---------------------------------------------------------------------------
# spaceload import [file]
# ---------------------------------------------------------------------------

@cli.command("import")
@click.argument("file", type=click.Path(exists=True), required=False)
def import_workspace(file: str | None) -> None:
    """Import a workspace from a YAML FILE (or stdin if omitted).

    Supports both the native export format and portable .spaceload.yaml share files.
    """
    if file:
        yaml_str = Path(file).read_text()
    else:
        if sys.stdin.isatty():
            click.echo("Provide a FILE argument or pipe YAML via stdin.", err=True)
            sys.exit(1)
        yaml_str = sys.stdin.read()

    import yaml as _yaml
    doc = _yaml.safe_load(yaml_str)

    if isinstance(doc, dict) and "spaceload" in doc:
        _import_share_file(yaml_str, doc)
    else:
        store = _get_store()
        try:
            store.import_yaml(yaml_str)
        finally:
            store.close()
        click.echo("Workspace imported successfully.")


def _import_share_file(raw_yaml: str, doc: dict) -> None:
    """Handle import of a .spaceload.yaml share file."""
    import yaml as _yaml
    from spaceload.share.token_resolver import detect_tokens, auto_tokens, resolve_tokens
    from spaceload.share.exporter import share_doc_to_store_yaml

    tokens = detect_tokens(raw_yaml)
    resolved = auto_tokens()

    # Prompt the user for any token we cannot resolve automatically
    for token in sorted(tokens - set(resolved)):
        resolved[token] = click.prompt(
            f"This workspace references {{{{{token}}}}}. Enter the local path"
        )

    resolved_yaml = resolve_tokens(raw_yaml, resolved)
    resolved_doc = _yaml.safe_load(resolved_yaml)

    store_yaml = share_doc_to_store_yaml(resolved_doc)
    store = _get_store()
    try:
        store.import_yaml(store_yaml)
    finally:
        store.close()

    _print_import_summary(resolved_doc)


def _print_import_summary(doc: dict) -> None:
    """Print a human-readable summary of what was imported."""
    name = doc.get("workspace", {}).get("name", "?")
    tabs = doc.get("browser", {}).get("tabs", [])
    ide = doc.get("ide", {})
    terminals = doc.get("terminals", [])
    vpn = doc.get("vpn")

    click.echo(f"\nImported workspace: {name}")
    if tabs:
        click.echo(f"  Browser tabs:  {len(tabs)}")
    if ide:
        click.echo(f"  IDE:           {ide.get('app', 'unknown')}")
    if vpn:
        click.echo(f"  VPN:           {vpn.get('vpn', 'unknown')}")
    if terminals:
        click.echo(f"  Terminals:     {len(terminals)}")
    click.echo(f"\nRun it with: spaceload run {name}")


# ---------------------------------------------------------------------------
# spaceload show <name>
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
# spaceload shell-hook <shell>
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
    from spaceload.shell.hooks import get_hook_script
    click.echo(get_hook_script(shell))
