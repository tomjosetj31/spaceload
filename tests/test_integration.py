"""Integration tests for ctx.

Tests that spawn the daemon subprocess, interact with it via the Unix socket,
and verify the resulting DB state.
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import pytest

from ctx.store.workspace_store import WorkspaceStore

_SOCKET_WAIT_TIMEOUT = 15.0  # seconds to wait for daemon socket to appear

# macOS Unix domain socket path limit is 104 bytes.  pytest's tmp_path uses
# /private/var/... which can easily exceed that.  We therefore create a
# dedicated short-lived directory under /tmp for socket + pid files only.
def _make_short_tmpdir() -> Path:
    """Return a short path suitable for Unix domain sockets on macOS."""
    d = Path(tempfile.mkdtemp(dir="/tmp", prefix="ctx_"))
    return d


def _wait_for_socket(sock_path: Path, timeout: float = _SOCKET_WAIT_TIMEOUT) -> bool:
    """Return True once the socket file exists, False on timeout."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if sock_path.exists():
            return True
        time.sleep(0.05)
    return False


def _send_message(sock_path: Path, message: dict, timeout: float = 10.0) -> dict:
    """Send a JSON message to the daemon socket and return the response."""
    payload = (json.dumps(message) + "\n").encode()
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.settimeout(timeout)
    try:
        sock.connect(str(sock_path))
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


def _build_daemon_cmd(
    workspace_name: str,
    sock_path: Path,
    pid_path: Path,
    db_path: Path,
    project_root: Path,
) -> list[str]:
    """Build the subprocess command to start the daemon with custom paths."""
    return [
        sys.executable,
        "-c",
        f"""
import sys
sys.path.insert(0, {str(project_root)!r})

import ctx.daemon.server as _m
from pathlib import Path

# Override module-level path constants before starting
_m._CTX_DIR = Path({str(sock_path.parent)!r})
_m._SOCKET_PATH = Path({str(sock_path)!r})
_m._PID_PATH = Path({str(pid_path)!r})

from ctx.daemon.server import RecorderDaemon
d = RecorderDaemon({workspace_name!r}, Path({str(db_path)!r}))
d.start()
""",
    ]


@pytest.fixture
def ctx_env(tmp_path: Path):
    """Provide isolated paths for daemon socket, PID, and DB.

    The socket and PID files live in a short /tmp directory to stay within
    macOS's 104-byte Unix domain socket path limit.  The DB lives in
    pytest's tmp_path (cleaned up automatically).
    """
    short_dir = _make_short_tmpdir()
    sock_path = short_dir / "d.sock"
    pid_path = short_dir / "d.pid"
    db_path = tmp_path / "ctx.db"
    project_root = Path(__file__).resolve().parents[1]
    try:
        yield {
            "sock_path": sock_path,
            "pid_path": pid_path,
            "db_path": db_path,
            "tmp_path": tmp_path,
            "project_root": project_root,
        }
    finally:
        # Clean up the short tmpdir
        import shutil
        shutil.rmtree(str(short_dir), ignore_errors=True)


class TestRecordStopIntegration:
    """Integration test: record empty session → stop → verify DB entry."""

    def test_record_empty_session_then_stop(self, ctx_env: dict) -> None:
        """Spawn daemon, send stop immediately, verify workspace in DB."""
        sock_path: Path = ctx_env["sock_path"]
        db_path: Path = ctx_env["db_path"]
        workspace_name = "test-workspace"

        daemon_cmd = _build_daemon_cmd(
            workspace_name=workspace_name,
            sock_path=sock_path,
            pid_path=ctx_env["pid_path"],
            db_path=db_path,
            project_root=ctx_env["project_root"],
        )

        proc = subprocess.Popen(
            daemon_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True,
        )

        try:
            # Wait for the socket to appear
            assert _wait_for_socket(sock_path), "Daemon socket did not appear in time"

            # Send stop command with no recorded actions
            response = _send_message(sock_path, {"command": "stop"})
            assert response["status"] == "ok"
            assert response["workspace"] == workspace_name
            assert response["action_count"] == 0

            # Give the daemon a moment to flush and exit
            proc.wait(timeout=5)

            # Verify workspace exists in the DB
            store = WorkspaceStore(db_path)
            try:
                ws = store.get_workspace(workspace_name)
                assert ws is not None, f"Workspace '{workspace_name}' not found in DB"
                assert ws["name"] == workspace_name
                assert ws["action_count"] == 0
                actions = store.get_actions(ws["id"])
                assert actions == []
            finally:
                store.close()

        finally:
            if proc.poll() is None:
                proc.terminate()
                proc.wait(timeout=3)

    def test_record_session_with_actions_then_stop(self, ctx_env: dict) -> None:
        """Spawn daemon, send actions, then stop, verify DB has correct count."""
        sock_path: Path = ctx_env["sock_path"]
        db_path: Path = ctx_env["db_path"]
        workspace_name = "test-with-actions"

        daemon_cmd = _build_daemon_cmd(
            workspace_name=workspace_name,
            sock_path=sock_path,
            pid_path=ctx_env["pid_path"],
            db_path=db_path,
            project_root=ctx_env["project_root"],
        )

        proc = subprocess.Popen(
            daemon_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True,
        )

        try:
            assert _wait_for_socket(sock_path), "Daemon socket did not appear in time"

            # Record two actions
            for url in ["https://github.com", "https://docs.python.org"]:
                resp = _send_message(
                    sock_path,
                    {
                        "command": "record_action",
                        "action": {
                            "type": "open_tab",
                            "data": {"url": url},
                            "timestamp": "2026-01-01T00:00:00+00:00",
                        },
                    },
                )
                assert resp["status"] == "ok"

            # Verify status shows 2 pending actions
            status = _send_message(sock_path, {"command": "status"})
            assert status["action_count"] == 2

            # Stop the daemon
            stop_resp = _send_message(sock_path, {"command": "stop"})
            assert stop_resp["status"] == "ok"
            assert stop_resp["action_count"] == 2

            proc.wait(timeout=5)

            # Verify DB
            store = WorkspaceStore(db_path)
            try:
                ws = store.get_workspace(workspace_name)
                assert ws is not None
                assert ws["action_count"] == 2
                actions = store.get_actions(ws["id"])
                assert len(actions) == 2
                urls = {a["data"]["url"] for a in actions}
                assert urls == {"https://github.com", "https://docs.python.org"}
            finally:
                store.close()

        finally:
            if proc.poll() is None:
                proc.terminate()
                proc.wait(timeout=3)

    def test_daemon_status_command(self, ctx_env: dict) -> None:
        """Status command returns current workspace name and action count."""
        sock_path: Path = ctx_env["sock_path"]
        db_path: Path = ctx_env["db_path"]
        workspace_name = "status-test"

        daemon_cmd = _build_daemon_cmd(
            workspace_name=workspace_name,
            sock_path=sock_path,
            pid_path=ctx_env["pid_path"],
            db_path=db_path,
            project_root=ctx_env["project_root"],
        )

        proc = subprocess.Popen(
            daemon_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True,
        )

        try:
            assert _wait_for_socket(sock_path), "Daemon socket did not appear in time"

            status = _send_message(sock_path, {"command": "status"})
            assert status["status"] == "ok"
            assert status["workspace"] == workspace_name
            assert status["action_count"] == 0

            _send_message(sock_path, {"command": "stop"})
            proc.wait(timeout=5)
        finally:
            if proc.poll() is None:
                proc.terminate()
                proc.wait(timeout=3)
