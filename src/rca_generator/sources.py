from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import yaml

from .timeline import TimelineEvent


def _parse_ts(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def load_alerts(path: str | Path) -> list[TimelineEvent]:
    data = yaml.safe_load(Path(path).read_text())
    return [
        TimelineEvent(
            timestamp=_parse_ts(a["timestamp"]),
            source="alert",
            text=f"[{a.get('severity', 'unknown').upper()}] {a['name']} on {a.get('service', 'unknown service')}",
        )
        for a in data.get("alerts", [])
    ]


def load_slack_thread(path: str | Path) -> list[TimelineEvent]:
    data = json.loads(Path(path).read_text())
    return [
        TimelineEvent(
            timestamp=_parse_ts(m["timestamp"]),
            source="slack",
            text=f"{m['user']}: {m['text']}",
        )
        for m in data.get("messages", [])
    ]


def load_logs(path: str | Path) -> list[TimelineEvent]:
    """Parse log lines of the form '<ISO8601 timestamp> <message>'."""
    events = []
    for line in Path(path).read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        ts_str, _, message = line.partition(" ")
        try:
            ts = _parse_ts(ts_str)
        except ValueError:
            continue
        events.append(TimelineEvent(timestamp=ts, source="log", text=message))
    return events


def load_metrics_summary(path: str | Path) -> str:
    """Metrics are passed to the LLM as plain-text context, not as timeline events."""
    data = yaml.safe_load(Path(path).read_text())
    return "\n".join(f"- {key}: {value}" for key, value in data.items())
