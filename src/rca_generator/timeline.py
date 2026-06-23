from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass
class TimelineEvent:
    timestamp: datetime
    source: str  # "alert" | "slack" | "log"
    text: str


def merge_timeline(*event_lists: list[TimelineEvent]) -> list[TimelineEvent]:
    events = [event for group in event_lists for event in group]
    return sorted(events, key=lambda e: e.timestamp)


def render_timeline(events: list[TimelineEvent]) -> str:
    lines = []
    for e in events:
        ts = e.timestamp.strftime("%Y-%m-%d %H:%M:%S UTC")
        lines.append(f"- [{ts}] ({e.source}) {e.text}")
    return "\n".join(lines)
