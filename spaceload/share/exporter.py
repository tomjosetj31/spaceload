"""Exporter — generates portable .spaceload.yaml share files."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

import yaml

from spaceload.share.sanitizer import sanitize_action, sanitize_path, _HOME


def _detect_project_root(actions: list[dict[str, Any]]) -> str | None:
    """Infer project root from IDE paths, falling back to terminal cwd."""
    for action in actions:
        if action.get("type") == "ide_project_open":
            path = action.get("path") or action.get("workspace_path")
            if path:
                return path
    for action in actions:
        if action.get("type") == "terminal_session_open":
            cwd = action.get("directory") or action.get("cwd")
            if cwd and cwd != _HOME:
                return cwd
    return None


def generate_share_yaml(
    workspace_name: str,
    actions: list[dict[str, Any]],
    description: str | None = None,
) -> str:
    """Build and return a portable .spaceload.yaml string."""
    from spaceload import __version__

    project_root = _detect_project_root(actions)

    # Collect grouped sections
    browser_tabs: list[str] = []
    browser_app: str | None = None
    ide_section: dict | None = None
    terminals: list[dict] = []
    vpn_section: dict | None = None
    removed_notes: list[str] = []

    for action in actions:
        atype = action.get("type", "")
        san = sanitize_action(action, project_root)

        if san.get("_removed"):
            removed_notes.append(
                f"# removed from '{atype}': {', '.join(san['_removed'])}"
            )

        if atype == "browser_tab_open":
            url = action.get("url", "")
            if url:
                browser_tabs.append(url)
            if not browser_app:
                browser_app = action.get("browser") or action.get("app")

        elif atype == "ide_project_open":
            raw_path = action.get("path") or action.get("workspace_path") or ""
            ide_section = {
                "app": action.get("app") or action.get("client"),
                "workspace_path": sanitize_path(raw_path, project_root) if raw_path else "{{PROJECT_ROOT}}",
            }

        elif atype == "terminal_session_open":
            raw_cwd = action.get("directory") or action.get("cwd") or ""
            term: dict[str, Any] = {
                "app": action.get("app"),
                "cwd": sanitize_path(raw_cwd, project_root) if raw_cwd else "{{PROJECT_ROOT}}",
            }
            cmd = action.get("command")
            if cmd:
                term["command"] = cmd
            terminals.append(term)

        elif atype == "vpn_connect":
            vpn_section = {"vpn": action.get("vpn") or action.get("app")}

    # Assemble document
    doc: dict[str, Any] = {}

    # --- spaceload metadata header ---
    meta: dict[str, Any] = {
        "version": 1,
        "share_id": uuid.uuid4().hex[:8],
        "created_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "platform": "macOS",
    }
    if description:
        meta["description"] = description
    doc["spaceload"] = meta

    # --- workspace ---
    ws: dict[str, Any] = {"name": workspace_name}
    if project_root:
        ws["project_root"] = "{{PROJECT_ROOT}}"
    doc["workspace"] = ws

    # --- sections ---
    if browser_tabs:
        doc["browser"] = {"app": browser_app, "tabs": browser_tabs}

    if ide_section:
        doc["ide"] = ide_section

    if terminals:
        doc["terminals"] = terminals

    if vpn_section:
        doc["vpn"] = vpn_section

    # Produce YAML then append any removal notes as comments at the top
    yaml_str = yaml.dump(doc, default_flow_style=False, allow_unicode=True, sort_keys=False)

    if removed_notes:
        header = "\n".join(removed_notes) + "\n"
        yaml_str = header + yaml_str

    return yaml_str


def share_doc_to_store_yaml(doc: dict[str, Any]) -> str:
    """Convert a resolved .spaceload.yaml doc back to the store's import format."""
    workspace_name = doc.get("workspace", {}).get("name", "imported")
    actions: list[dict[str, Any]] = []

    for tab in doc.get("browser", {}).get("tabs", []):
        actions.append({
            "type": "browser_tab_open",
            "url": tab,
            "browser": doc.get("browser", {}).get("app"),
        })

    ide = doc.get("ide")
    if ide:
        actions.append({
            "type": "ide_project_open",
            "app": ide.get("app"),
            "path": ide.get("workspace_path"),
        })

    for term in doc.get("terminals", []):
        a: dict[str, Any] = {
            "type": "terminal_session_open",
            "app": term.get("app"),
            "directory": term.get("cwd"),
        }
        if term.get("command"):
            a["command"] = term["command"]
        actions.append(a)

    vpn = doc.get("vpn")
    if vpn:
        actions.append({
            "type": "vpn_connect",
            "vpn": vpn.get("vpn"),
        })

    payload = {
        "workspace": {"name": workspace_name},
        "actions": actions,
    }
    return yaml.dump(payload, default_flow_style=False, allow_unicode=True, sort_keys=False)
