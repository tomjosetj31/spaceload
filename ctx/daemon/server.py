"""Unix socket recorder daemon for ctx.

Run as a subprocess by `ctx record <name>`. Listens for JSON messages on a
Unix domain socket, accumulates actions in memory, and flushes them to the
SQLite store on a stop command.

Usage (internal — spawned by the CLI):
    python -m ctx.daemon.server <workspace_name> [--db <db_path>]
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import socket
import sys
from pathlib import Path

# Make sure the project root is importable when run as __main__
_PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from ctx.store.workspace_store import WorkspaceStore

_CTX_DIR = Path.home() / ".ctx"
_SOCKET_PATH = _CTX_DIR / "daemon.sock"
_PID_PATH = _CTX_DIR / "daemon.pid"


class RecorderDaemon:
    """In-process Unix socket server that records workspace actions."""

    def __init__(self, workspace_name: str, db_path: Path) -> None:
        self.workspace_name = workspace_name
        self.db_path = db_path
        self._actions: list[dict] = []
        self._running = False
        self._sock: socket.socket | None = None
        self._workspace_id: int | None = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Initialise the store entry, write PID, and start the event loop."""
        _CTX_DIR.mkdir(parents=True, exist_ok=True)

        # Write PID file
        _PID_PATH.write_text(str(os.getpid()))

        # Create workspace in the store
        store = WorkspaceStore(self.db_path)
        self._workspace_id = store.create_workspace(self.workspace_name)
        store.close()

        # Remove stale socket file
        if _SOCKET_PATH.exists():
            _SOCKET_PATH.unlink()

        self._sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self._sock.bind(str(_SOCKET_PATH))
        self._sock.listen(5)
        self._sock.settimeout(1.0)  # allows periodic checks of self._running

        self._running = True

        # Handle SIGTERM for clean shutdown
        signal.signal(signal.SIGTERM, self._handle_signal)

        self._loop()

    def _handle_signal(self, signum: int, frame: object) -> None:
        self._shutdown()

    def _loop(self) -> None:
        """Accept connections and process messages until stopped."""
        assert self._sock is not None
        while self._running:
            try:
                conn, _ = self._sock.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            try:
                self._handle_connection(conn)
            finally:
                conn.close()

        self._cleanup()

    def _handle_connection(self, conn: socket.socket) -> None:
        """Read a JSON message from a connection and respond."""
        data = b""
        while True:
            chunk = conn.recv(4096)
            if not chunk:
                break
            data += chunk
            if b"\n" in data:
                break

        if not data:
            return

        try:
            msg = json.loads(data.decode().strip())
        except json.JSONDecodeError:
            conn.sendall(b'{"status": "error", "reason": "invalid JSON"}\n')
            return

        command = msg.get("command")

        if command == "stop":
            action_count = self._flush_to_store()
            response = {
                "status": "ok",
                "workspace": self.workspace_name,
                "action_count": action_count,
            }
            conn.sendall((json.dumps(response) + "\n").encode())
            self._running = False

        elif command == "status":
            response = {
                "status": "ok",
                "workspace": self.workspace_name,
                "action_count": len(self._actions),
            }
            conn.sendall((json.dumps(response) + "\n").encode())

        elif command == "record_action":
            action = msg.get("action", {})
            self._actions.append(action)
            conn.sendall(b'{"status": "ok"}\n')

        else:
            conn.sendall(b'{"status": "error", "reason": "unknown command"}\n')

    # ------------------------------------------------------------------
    # Store flushing
    # ------------------------------------------------------------------

    def _flush_to_store(self) -> int:
        """Write accumulated actions to the store. Returns action count."""
        store = WorkspaceStore(self.db_path)
        try:
            if self._workspace_id is not None:
                store.save_actions(self._workspace_id, self._actions)
            return len(self._actions)
        finally:
            store.close()

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    def _shutdown(self) -> None:
        self._running = False

    def _cleanup(self) -> None:
        if self._sock:
            try:
                self._sock.close()
            except OSError:
                pass
        if _SOCKET_PATH.exists():
            _SOCKET_PATH.unlink(missing_ok=True)
        if _PID_PATH.exists():
            _PID_PATH.unlink(missing_ok=True)


# ------------------------------------------------------------------
# Entry point
# ------------------------------------------------------------------

def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="ctx recorder daemon")
    parser.add_argument("workspace_name", help="Name of the workspace being recorded")
    parser.add_argument(
        "--db",
        default=str(_CTX_DIR / "ctx.db"),
        help="Path to the SQLite database (default: ~/.ctx/ctx.db)",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    daemon = RecorderDaemon(
        workspace_name=args.workspace_name,
        db_path=Path(args.db),
    )
    daemon.start()
