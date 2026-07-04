"""Pluggable evidence connectors — one per upstream system.

Each connector maps 1:1 to an MCP server in the production design (Slack,
Jira, Grafana, Sumo Logic). The demo ships file-backed implementations behind
the same interface so the whole pipeline runs offline: the orchestrator only
sees the `Connector` protocol, so swapping a file reader for a real MCP client
— or adding a new source entirely — is a registry entry, not a rewrite.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable

import yaml

from .timeline import TimelineEvent


@dataclass
class Evidence:
    source: str
    available: bool
    events: list[TimelineEvent] = field(default_factory=list)
    context: str = ""  # prose block injected into stage prompts


@dataclass(frozen=True)
class Connector:
    name: str
    loader: Callable[[Path], Evidence]

    def fetch(self, incident_dir: Path) -> Evidence:
        return self.loader(incident_dir)


def _parse_ts(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _load_slack(incident_dir: Path) -> Evidence:
    path = incident_dir / "slack_thread.json"
    if not path.exists():
        return Evidence(source="slack", available=False)
    data = json.loads(path.read_text())
    events = [
        TimelineEvent(
            timestamp=_parse_ts(m["timestamp"]),
            source="slack",
            text=f"{m['user']}: {m['text']}",
        )
        for m in data.get("messages", [])
    ]
    participants = sorted({m["user"] for m in data.get("messages", [])})
    context = f"Incident-channel participants: {', '.join(participants)}"
    return Evidence(source="slack", available=bool(events), events=events, context=context)


def _load_jira(incident_dir: Path) -> Evidence:
    path = incident_dir / "tickets.yaml"
    if not path.exists():
        return Evidence(source="jira", available=False)
    data = yaml.safe_load(path.read_text())
    tickets = data.get("tickets", [])
    events = [
        TimelineEvent(
            timestamp=_parse_ts(t["created"]),
            source="jira",
            text=f"{t['key']} filed: {t['summary']}",
        )
        for t in tickets
    ]
    context = "\n".join(
        f"- {t['key']} [{t.get('status', 'unknown')}] assignee={t.get('assignee', 'unassigned')}: {t['summary']}"
        for t in tickets
    )
    return Evidence(source="jira", available=bool(tickets), events=events, context=context)


def _load_monitoring(incident_dir: Path) -> Evidence:
    alerts_path = incident_dir / "alerts.yaml"
    metrics_path = incident_dir / "metrics_summary.yaml"
    events: list[TimelineEvent] = []
    context = ""
    if alerts_path.exists():
        data = yaml.safe_load(alerts_path.read_text())
        events = [
            TimelineEvent(
                timestamp=_parse_ts(a["timestamp"]),
                source="alert",
                text=f"[{a.get('severity', 'unknown').upper()}] {a['name']} on {a.get('service', 'unknown service')}",
            )
            for a in data.get("alerts", [])
        ]
    if metrics_path.exists():
        data = yaml.safe_load(metrics_path.read_text())
        context = "\n".join(f"- {key}: {value}" for key, value in data.items())
    return Evidence(
        source="monitoring",
        available=bool(events or context),
        events=events,
        context=context,
    )


def _load_logs(incident_dir: Path) -> Evidence:
    """Parse log lines of the form '<ISO8601 timestamp> <message>'."""
    path = incident_dir / "logs.txt"
    if not path.exists():
        return Evidence(source="logs", available=False)
    events = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        ts_str, _, message = line.partition(" ")
        try:
            ts = _parse_ts(ts_str)
        except ValueError:
            continue
        events.append(TimelineEvent(timestamp=ts, source="log", text=message))
    return Evidence(source="logs", available=bool(events), events=events)


REGISTRY: tuple[Connector, ...] = (
    Connector("slack", _load_slack),
    Connector("jira", _load_jira),
    Connector("monitoring", _load_monitoring),
    Connector("logs", _load_logs),
)


def fetch_all(incident_dir: str | Path) -> dict[str, Evidence]:
    incident_dir = Path(incident_dir)
    return {c.name: c.fetch(incident_dir) for c in REGISTRY}
