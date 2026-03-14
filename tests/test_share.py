"""Tests for spaceload share — sanitizer, exporter, token_resolver, and CLI."""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml
from click.testing import CliRunner

from spaceload.share.sanitizer import sanitize_path, sanitize_action, _HOME
from spaceload.share.exporter import generate_share_yaml, share_doc_to_store_yaml
from spaceload.share.token_resolver import detect_tokens, auto_tokens, resolve_tokens


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def project_root():
    return f"{_HOME}/code/payments"


@pytest.fixture
def sample_actions(project_root):
    return [
        {
            "type": "browser_tab_open",
            "url": "http://localhost:3000",
            "browser": "Arc",
        },
        {
            "type": "browser_tab_open",
            "url": "https://stripe.com/docs/api",
            "browser": "Arc",
        },
        {
            "type": "ide_project_open",
            "app": "Visual Studio Code",
            "path": project_root,
        },
        {
            "type": "terminal_session_open",
            "app": "iTerm2",
            "directory": project_root,
            "command": "npm run dev",
        },
        {
            "type": "vpn_connect",
            "vpn": "tailscale",
        },
    ]


# ---------------------------------------------------------------------------
# sanitizer.py tests
# ---------------------------------------------------------------------------

class TestSanitizePath:
    def test_replaces_home_prefix(self):
        path = f"{_HOME}/code/myproject"
        result = sanitize_path(path)
        assert result == "{{HOME}}/code/myproject"

    def test_replaces_exact_home(self):
        result = sanitize_path(_HOME)
        assert result == "{{HOME}}"

    def test_replaces_project_root(self):
        pr = f"{_HOME}/code/payments"
        path = f"{pr}/src/index.js"
        result = sanitize_path(path, project_root=pr)
        assert result == "{{PROJECT_ROOT}}/src/index.js"

    def test_replaces_exact_project_root(self):
        pr = f"{_HOME}/code/payments"
        result = sanitize_path(pr, project_root=pr)
        assert result == "{{PROJECT_ROOT}}"

    def test_project_root_takes_priority_over_home(self):
        pr = f"{_HOME}/code/payments"
        path = f"{pr}/src"
        result = sanitize_path(path, project_root=pr)
        assert "{{PROJECT_ROOT}}" in result
        assert "{{HOME}}" not in result

    def test_preserves_unrelated_path(self):
        result = sanitize_path("/usr/local/bin/python")
        assert result == "/usr/local/bin/python"

    def test_expands_tilde(self):
        result = sanitize_path("~/code/project")
        assert result.startswith("{{HOME}}")

    def test_preserves_localhost_url(self):
        # localhost URLs are not paths — sanitize_path is not called on them
        result = sanitize_path("http://localhost:3000")
        assert result == "http://localhost:3000"


class TestSanitizeAction:
    def test_strips_secret_key_named_token(self):
        action = {"type": "browser_tab_open", "url": "https://example.com", "token": "abc123"}
        result = sanitize_action(action)
        assert "token" not in result
        assert "token" in result["_removed"]

    def test_strips_password_field(self):
        action = {"type": "vpn_connect", "vpn": "tailscale", "password": "hunter2"}
        result = sanitize_action(action)
        assert "password" not in result
        assert "password" in result["_removed"]

    def test_strips_private_ip_value(self):
        action = {"type": "vpn_connect", "server": "10.0.0.1"}
        result = sanitize_action(action)
        assert "server" not in result
        assert "server" in result["_removed"]

    def test_strips_172_private_ip(self):
        action = {"type": "app_open", "server": "172.16.0.1"}
        result = sanitize_action(action)
        assert "server" not in result

    def test_strips_192_168_private_ip(self):
        action = {"type": "app_open", "server": "192.168.1.100"}
        result = sanitize_action(action)
        assert "server" not in result

    def test_preserves_localhost_url(self):
        action = {"type": "browser_tab_open", "url": "http://localhost:3000"}
        result = sanitize_action(action)
        assert result["url"] == "http://localhost:3000"
        assert "_removed" not in result

    def test_preserves_public_url(self):
        action = {"type": "browser_tab_open", "url": "https://github.com/org/repo"}
        result = sanitize_action(action)
        assert result["url"] == "https://github.com/org/repo"

    def test_sanitizes_path_field(self, project_root):
        action = {"type": "ide_project_open", "app": "VS Code", "path": project_root}
        result = sanitize_action(action, project_root=project_root)
        assert result["path"] == "{{PROJECT_ROOT}}"

    def test_no_removed_when_clean(self):
        action = {"type": "browser_tab_open", "url": "https://example.com", "browser": "Arc"}
        result = sanitize_action(action)
        assert "_removed" not in result

    def test_preserves_type_field(self):
        action = {"type": "app_open", "app": "Slack"}
        result = sanitize_action(action)
        assert result["type"] == "app_open"


# ---------------------------------------------------------------------------
# exporter.py tests
# ---------------------------------------------------------------------------

class TestGenerateShareYaml:
    def test_has_spaceload_header(self, sample_actions):
        yaml_str = generate_share_yaml("payments", sample_actions)
        doc = yaml.safe_load(yaml_str)
        assert "spaceload" in doc

    def test_header_has_required_fields(self, sample_actions):
        yaml_str = generate_share_yaml("payments", sample_actions)
        doc = yaml.safe_load(yaml_str)
        meta = doc["spaceload"]
        assert meta["version"] == 1
        assert "share_id" in meta
        assert "created_at" in meta
        assert meta["platform"] == "macOS"

    def test_share_id_is_8_chars(self, sample_actions):
        yaml_str = generate_share_yaml("payments", sample_actions)
        doc = yaml.safe_load(yaml_str)
        assert len(doc["spaceload"]["share_id"]) == 8

    def test_each_call_generates_unique_share_id(self, sample_actions):
        id1 = yaml.safe_load(generate_share_yaml("ws", sample_actions))["spaceload"]["share_id"]
        id2 = yaml.safe_load(generate_share_yaml("ws", sample_actions))["spaceload"]["share_id"]
        assert id1 != id2

    def test_workspace_name_preserved(self, sample_actions):
        doc = yaml.safe_load(generate_share_yaml("payments", sample_actions))
        assert doc["workspace"]["name"] == "payments"

    def test_browser_tabs_present(self, sample_actions):
        doc = yaml.safe_load(generate_share_yaml("payments", sample_actions))
        assert "browser" in doc
        assert "http://localhost:3000" in doc["browser"]["tabs"]
        assert "https://stripe.com/docs/api" in doc["browser"]["tabs"]

    def test_ide_section_present(self, sample_actions):
        doc = yaml.safe_load(generate_share_yaml("payments", sample_actions))
        assert doc["ide"]["app"] == "Visual Studio Code"
        assert "{{PROJECT_ROOT}}" in doc["ide"]["workspace_path"]

    def test_terminal_section_present(self, sample_actions):
        doc = yaml.safe_load(generate_share_yaml("payments", sample_actions))
        assert len(doc["terminals"]) == 1
        assert doc["terminals"][0]["command"] == "npm run dev"

    def test_paths_tokenized(self, sample_actions):
        yaml_str = generate_share_yaml("payments", sample_actions)
        assert _HOME not in yaml_str
        assert "{{PROJECT_ROOT}}" in yaml_str or "{{HOME}}" in yaml_str

    def test_description_included(self, sample_actions):
        doc = yaml.safe_load(generate_share_yaml("payments", sample_actions, description="My workspace"))
        assert doc["spaceload"]["description"] == "My workspace"

    def test_no_description_by_default(self, sample_actions):
        doc = yaml.safe_load(generate_share_yaml("payments", sample_actions))
        assert "description" not in doc["spaceload"]

    def test_empty_actions_produces_valid_yaml(self):
        yaml_str = generate_share_yaml("empty", [])
        doc = yaml.safe_load(yaml_str)
        assert doc["workspace"]["name"] == "empty"

    def test_removed_secrets_noted_as_comments(self):
        actions = [{"type": "vpn_connect", "vpn": "tailscale", "password": "secret"}]
        yaml_str = generate_share_yaml("ws", actions)
        assert "# removed" in yaml_str


class TestShareDocToStoreYaml:
    def test_roundtrip_browser_tabs(self):
        doc = {
            "spaceload": {"version": 1, "share_id": "abc", "created_at": "2026-01-01", "platform": "macOS"},
            "workspace": {"name": "test"},
            "browser": {"app": "Arc", "tabs": ["https://github.com"]},
        }
        store_yaml = share_doc_to_store_yaml(doc)
        payload = yaml.safe_load(store_yaml)
        actions = payload["actions"]
        assert any(a["type"] == "browser_tab_open" and a["url"] == "https://github.com" for a in actions)

    def test_roundtrip_ide(self):
        doc = {
            "workspace": {"name": "test"},
            "ide": {"app": "VS Code", "workspace_path": "/code/project"},
        }
        payload = yaml.safe_load(share_doc_to_store_yaml(doc))
        assert any(a["type"] == "ide_project_open" for a in payload["actions"])

    def test_roundtrip_terminals(self):
        doc = {
            "workspace": {"name": "test"},
            "terminals": [{"app": "iTerm2", "cwd": "/code", "command": "npm start"}],
        }
        payload = yaml.safe_load(share_doc_to_store_yaml(doc))
        term = next(a for a in payload["actions"] if a["type"] == "terminal_session_open")
        assert term["command"] == "npm start"

    def test_roundtrip_vpn(self):
        doc = {
            "workspace": {"name": "test"},
            "vpn": {"vpn": "tailscale"},
        }
        payload = yaml.safe_load(share_doc_to_store_yaml(doc))
        assert any(a["type"] == "vpn_connect" for a in payload["actions"])


# ---------------------------------------------------------------------------
# token_resolver.py tests
# ---------------------------------------------------------------------------

class TestDetectTokens:
    def test_finds_project_root(self):
        assert "PROJECT_ROOT" in detect_tokens("path: {{PROJECT_ROOT}}/src")

    def test_finds_home(self):
        assert "HOME" in detect_tokens("dir: {{HOME}}/code")

    def test_finds_multiple(self):
        tokens = detect_tokens("{{PROJECT_ROOT}} and {{HOME}}")
        assert tokens == {"PROJECT_ROOT", "HOME"}

    def test_empty_when_none(self):
        assert detect_tokens("no tokens here") == set()


class TestAutoTokens:
    def test_home_resolved(self):
        tokens = auto_tokens()
        assert "HOME" in tokens
        assert tokens["HOME"] == str(Path.home())


class TestResolveTokens:
    def test_replaces_project_root(self):
        result = resolve_tokens("{{PROJECT_ROOT}}/src", {"PROJECT_ROOT": "/code/app"})
        assert result == "/code/app/src"

    def test_replaces_home(self):
        result = resolve_tokens("{{HOME}}/code", {"HOME": "/Users/tom"})
        assert result == "/Users/tom/code"

    def test_unknown_token_left_as_is(self):
        result = resolve_tokens("{{UNKNOWN}}", {})
        assert result == "{{UNKNOWN}}"

    def test_replaces_all_occurrences(self):
        result = resolve_tokens("{{X}}/a and {{X}}/b", {"X": "/root"})
        assert result == "/root/a and /root/b"


# ---------------------------------------------------------------------------
# CLI tests
# ---------------------------------------------------------------------------

class TestShareCommand:
    def _make_store_with_workspace(self, tmp_path):
        from spaceload.store.workspace_store import WorkspaceStore
        db = tmp_path / "test.db"
        store = WorkspaceStore(db)
        ws_id = store.create_workspace("payments")
        store.save_actions(ws_id, [
            {"type": "browser_tab_open", "url": "http://localhost:3000", "browser": "Arc"},
            {"type": "ide_project_open", "app": "VS Code", "path": f"{_HOME}/code/payments"},
        ])
        store.close()
        return db

    def test_share_writes_file(self, runner, tmp_path):
        db = self._make_store_with_workspace(tmp_path)
        out = tmp_path / "payments.spaceload.yaml"
        with patch("spaceload.cli.main._get_store") as mock_store_fn:
            from spaceload.store.workspace_store import WorkspaceStore
            mock_store_fn.return_value = WorkspaceStore(db)
            result = runner.invoke(
                __import__("spaceload.cli.main", fromlist=["cli"]).cli,
                ["share", "payments", "--output", str(out)],
            )
        assert result.exit_code == 0
        assert out.exists()
        doc = yaml.safe_load(out.read_text())
        assert "spaceload" in doc

    def test_share_not_found(self, runner, tmp_path):
        db = tmp_path / "empty.db"
        with patch("spaceload.cli.main._get_store") as mock_store_fn:
            from spaceload.store.workspace_store import WorkspaceStore
            mock_store_fn.return_value = WorkspaceStore(db)
            result = runner.invoke(
                __import__("spaceload.cli.main", fromlist=["cli"]).cli,
                ["share", "nonexistent"],
            )
        assert result.exit_code != 0

    def test_share_print_stdout(self, runner, tmp_path):
        db = self._make_store_with_workspace(tmp_path)
        with patch("spaceload.cli.main._get_store") as mock_store_fn:
            from spaceload.store.workspace_store import WorkspaceStore
            mock_store_fn.return_value = WorkspaceStore(db)
            result = runner.invoke(
                __import__("spaceload.cli.main", fromlist=["cli"]).cli,
                ["share", "payments", "--print"],
            )
        assert result.exit_code == 0
        doc = yaml.safe_load(result.output)
        assert "spaceload" in doc

    def test_share_clipboard(self, runner, tmp_path):
        db = self._make_store_with_workspace(tmp_path)
        with patch("spaceload.cli.main._get_store") as mock_store_fn, \
             patch("spaceload.cli.main.subprocess.run") as mock_run:
            from spaceload.store.workspace_store import WorkspaceStore
            mock_store_fn.return_value = WorkspaceStore(db)
            mock_run.return_value = MagicMock(returncode=0)
            result = runner.invoke(
                __import__("spaceload.cli.main", fromlist=["cli"]).cli,
                ["share", "payments", "--clipboard"],
            )
        assert result.exit_code == 0
        assert "clipboard" in result.output
        mock_run.assert_called_once()
        assert mock_run.call_args[0][0] == ["pbcopy"]

    def test_share_with_description(self, runner, tmp_path):
        db = self._make_store_with_workspace(tmp_path)
        out = tmp_path / "ws.spaceload.yaml"
        with patch("spaceload.cli.main._get_store") as mock_store_fn:
            from spaceload.store.workspace_store import WorkspaceStore
            mock_store_fn.return_value = WorkspaceStore(db)
            result = runner.invoke(
                __import__("spaceload.cli.main", fromlist=["cli"]).cli,
                ["share", "payments", "--output", str(out), "--description", "My workspace"],
            )
        assert result.exit_code == 0
        doc = yaml.safe_load(out.read_text())
        assert doc["spaceload"]["description"] == "My workspace"


class TestImportShareFile:
    def _make_share_yaml(self, tmp_path, project_root_token=True):
        doc = {
            "spaceload": {
                "version": 1,
                "share_id": "abc12345",
                "created_at": "2026-03-15T10:00:00Z",
                "platform": "macOS",
            },
            "workspace": {"name": "payments", "project_root": "{{PROJECT_ROOT}}"},
            "browser": {"app": "Arc", "tabs": ["http://localhost:3000", "https://github.com"]},
            "ide": {"app": "VS Code", "workspace_path": "{{PROJECT_ROOT}}"},
            "terminals": [{"app": "iTerm2", "cwd": "{{PROJECT_ROOT}}", "command": "npm run dev"}],
        }
        f = tmp_path / "payments.spaceload.yaml"
        f.write_text(yaml.dump(doc, default_flow_style=False))
        return f

    def test_import_share_file_prompts_for_project_root(self, runner, tmp_path):
        share_file = self._make_share_yaml(tmp_path)
        db = tmp_path / "test.db"
        with patch("spaceload.cli.main._get_store") as mock_store_fn:
            from spaceload.store.workspace_store import WorkspaceStore
            store = WorkspaceStore(db)
            mock_store_fn.return_value = store
            result = runner.invoke(
                __import__("spaceload.cli.main", fromlist=["cli"]).cli,
                ["import", str(share_file)],
                input=f"{_HOME}/code/payments\n",
            )
        assert result.exit_code == 0
        assert "PROJECT_ROOT" in result.output
        assert "Imported workspace: payments" in result.output

    def test_import_share_file_resolves_home_automatically(self, runner, tmp_path):
        doc = {
            "spaceload": {"version": 1, "share_id": "x", "created_at": "2026-01-01", "platform": "macOS"},
            "workspace": {"name": "home-ws"},
            "ide": {"app": "VS Code", "workspace_path": "{{HOME}}/code"},
        }
        f = tmp_path / "ws.spaceload.yaml"
        f.write_text(yaml.dump(doc))
        db = tmp_path / "test.db"
        with patch("spaceload.cli.main._get_store") as mock_store_fn:
            from spaceload.store.workspace_store import WorkspaceStore
            mock_store_fn.return_value = WorkspaceStore(db)
            result = runner.invoke(
                __import__("spaceload.cli.main", fromlist=["cli"]).cli,
                ["import", str(f)],
            )
        assert result.exit_code == 0
        assert "Imported workspace: home-ws" in result.output

    def test_import_prints_summary(self, runner, tmp_path):
        share_file = self._make_share_yaml(tmp_path)
        db = tmp_path / "test.db"
        with patch("spaceload.cli.main._get_store") as mock_store_fn:
            from spaceload.store.workspace_store import WorkspaceStore
            mock_store_fn.return_value = WorkspaceStore(db)
            result = runner.invoke(
                __import__("spaceload.cli.main", fromlist=["cli"]).cli,
                ["import", str(share_file)],
                input=f"{_HOME}/code/payments\n",
            )
        assert "Browser tabs:  2" in result.output
        assert "IDE:           VS Code" in result.output
        assert "spaceload run payments" in result.output

    def test_import_native_yaml_still_works(self, runner, tmp_path):
        native = {
            "workspace": {"name": "native-ws", "created_at": "2026-01-01"},
            "actions": [{"type": "app_open", "app": "Slack"}],
        }
        f = tmp_path / "native.yaml"
        f.write_text(yaml.dump(native))
        db = tmp_path / "test.db"
        with patch("spaceload.cli.main._get_store") as mock_store_fn:
            from spaceload.store.workspace_store import WorkspaceStore
            mock_store_fn.return_value = WorkspaceStore(db)
            result = runner.invoke(
                __import__("spaceload.cli.main", fromlist=["cli"]).cli,
                ["import", str(f)],
            )
        assert result.exit_code == 0
        assert "imported successfully" in result.output
