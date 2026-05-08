"""Orchestrates the full spaceload focus flow."""

from __future__ import annotations

import click

from spaceload.focus.focus_planner import FocusPlan, FocusPlanner
from spaceload.focus.focus_executor import FocusExecutor


def _print_dry_run(plan: FocusPlan) -> None:
    """Print the dry-run plan in the format specified by the issue."""
    click.echo("Dry run — no changes will be made.")
    click.echo(f"Focus plan: {plan.workspace_name}\n")

    ws_tabs: dict[str, str] = getattr(plan, "_ws_tabs", {})
    ide_projects: list[tuple[str, str]] = getattr(plan, "_ide_projects", [])
    terminal_sessions: list[tuple[str, str]] = getattr(plan, "_terminal_sessions", [])
    services_already_running: list[str] = getattr(plan, "_services_already_running", [])

    if plan.tabs_to_open:
        click.echo("Open (not yet open):")
        for url in plan.tabs_to_open:
            click.echo(f"  + {url}")
        click.echo()

    if plan.tabs_to_close:
        click.echo("Close (not in workspace):")
        for url in plan.tabs_to_close:
            click.echo(f"  - {url}")
        click.echo()

    if plan.tabs_to_keep:
        click.echo("Keep (already open + in workspace):")
        for url in plan.tabs_to_keep:
            click.echo(f"  = {url}")
        click.echo()

    if plan.keep_matched:
        click.echo("Keep (matched --keep pattern):")
        for url in plan.keep_matched:
            click.echo(f"  ~ {url}")
        click.echo()

    if ide_projects:
        click.echo("IDE:")
        for client, path in ide_projects:
            click.echo(f"  → Open {client} at {path}")
        click.echo()

    if plan.services_to_start or services_already_running:
        click.echo("Docker:")
        for name in plan.services_to_start:
            click.echo(f"  → Start {name} (not running)")
        for name in services_already_running:
            click.echo(f"  → {name} already running — no action")
        click.echo()

    if terminal_sessions:
        click.echo("Terminals:")
        for app, directory in terminal_sessions:
            click.echo(f"  → Open {app} at {directory}")
        click.echo()

    click.echo("Nothing executed.")


def _print_summary(plan: FocusPlan, stats) -> None:
    """Print a post-execution summary."""
    click.echo(f"\n[focus] Done — {plan.workspace_name}")
    parts = []
    if stats.opened:
        parts.append(f"{stats.opened} opened")
    if stats.closed:
        parts.append(f"{stats.closed} closed")
    if stats.kept:
        parts.append(f"{stats.kept} kept")
    if stats.skipped:
        parts.append(f"{stats.skipped} skipped")
    if stats.failed:
        parts.append(f"{len(stats.failed)} failed")
    click.echo("  " + ", ".join(parts) if parts else "  nothing to do")
    if stats.failed:
        click.echo("  Failed:")
        for item in stats.failed:
            click.echo(f"    - {item}")


def run_focus(
    workspace_name: str,
    actions: list[dict],
    *,
    keep_patterns: list[str],
    yes: bool,
    dry_run: bool,
    no_close: bool,
    close_terminals: bool,
    verbose: bool,
) -> None:
    """Build a FocusPlan then either print (dry-run) or execute it."""
    click.echo(f"spaceload focus: {workspace_name}\n")

    planner = FocusPlanner()
    plan, can_read_tabs = planner.build(
        workspace_actions=actions,
        keep_patterns=list(keep_patterns),
        no_close=no_close,
        close_terminals=close_terminals,
    )
    plan.workspace_name = workspace_name

    if not can_read_tabs and not no_close:
        click.echo(
            "[warn] Could not read current browser tabs. "
            "Skipping tab cleanup — only new tabs will be opened.\n"
        )
        plan.tabs_to_close = []

    if dry_run:
        _print_dry_run(plan)
        return

    executor = FocusExecutor()
    stats = executor.execute(plan, yes=yes, verbose=verbose)
    _print_summary(plan, stats)
