"""Live recording state — accumulates events and tracks elapsed time.

RecordingView is a pure data container: it holds everything the renderer
needs to draw the panel. Call update_events() each poll cycle to ingest
new events from the EventPoller.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import NamedTuple

from spaceload.tui.event_poller import RecordingEvent


class BrowserEntry(NamedTuple):
    url: str
    timestamp: datetime


class IDEEntry(NamedTuple):
    path: str
    client: str
    timestamp: datetime


class TerminalEntry(NamedTuple):
    directory: str
    app: str
    timestamp: datetime


class RecordingView:
    """Mutable state snapshot for the live recording TUI panel.

    All mutation goes through update_events(); all reads are via
    properties so the renderer never writes state accidentally.
    """

    def __init__(self, workspace_name: str) -> None:
        self.workspace_name = workspace_name
        self.start_time: datetime = datetime.now(timezone.utc)

        self._browser_tabs: dict[str, list[BrowserEntry]] = {}
        self._ide_projects: dict[str, list[IDEEntry]] = {}
        self._terminal_sessions: dict[str, list[TerminalEntry]] = {}
        self._vpn_connected: bool = False
        self._vpn_label: str = "not connected"
        self._total_events: int = 0

    # ------------------------------------------------------------------
    # Mutation
    # ------------------------------------------------------------------

    def update_events(self, events: list[RecordingEvent]) -> None:
        """Ingest a batch of new events from the EventPoller."""
        for event in events:
            self._total_events += 1
            adapter = event.adapter

            if adapter == "browser":
                browser = event.raw.get("browser", "browser")
                self._browser_tabs.setdefault(browser, []).append(
                    BrowserEntry(url=event.label, timestamp=event.timestamp)
                )

            elif adapter == "ide":
                client = event.raw.get("client", "IDE")
                self._ide_projects.setdefault(client, []).append(
                    IDEEntry(path=event.label, client=client, timestamp=event.timestamp)
                )

            elif adapter == "terminal":
                app = event.raw.get("app", "terminal")
                self._terminal_sessions.setdefault(app, []).append(
                    TerminalEntry(
                        directory=event.label, app=app, timestamp=event.timestamp
                    )
                )

            elif adapter == "vpn":
                if event.action == "connected":
                    self._vpn_connected = True
                    self._vpn_label = event.label
                elif event.action == "disconnected":
                    self._vpn_connected = False
                    self._vpn_label = "not connected"

    # ------------------------------------------------------------------
    # Accessors
    # ------------------------------------------------------------------

    def elapsed(self) -> float:
        """Seconds elapsed since recording started."""
        return (datetime.now(timezone.utc) - self.start_time).total_seconds()

    def elapsed_str(self) -> str:
        """Elapsed time as HH:MM:SS."""
        secs = int(self.elapsed())
        h, rem = divmod(secs, 3600)
        m, s = divmod(rem, 60)
        return f"{h:02d}:{m:02d}:{s:02d}"

    @property
    def browser_tabs(self) -> dict[str, list[BrowserEntry]]:
        return self._browser_tabs

    @property
    def ide_projects(self) -> dict[str, list[IDEEntry]]:
        return self._ide_projects

    @property
    def terminal_sessions(self) -> dict[str, list[TerminalEntry]]:
        return self._terminal_sessions

    @property
    def vpn_connected(self) -> bool:
        return self._vpn_connected

    @property
    def vpn_label(self) -> str:
        return self._vpn_label

    @property
    def total_events(self) -> int:
        return self._total_events

    def summary_counts(self) -> dict:
        """Aggregated counts for the final summary display."""
        return {
            "browser": {b: len(tabs) for b, tabs in self._browser_tabs.items()},
            "ide": {c: len(projs) for c, projs in self._ide_projects.items()},
            "terminal_count": sum(
                len(sessions) for sessions in self._terminal_sessions.values()
            ),
            "terminal_app": next(iter(self._terminal_sessions), None),
            "vpn": self._vpn_label if self._vpn_connected else "not connected",
        }
