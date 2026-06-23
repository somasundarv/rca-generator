from datetime import datetime, timezone

from rca_generator.timeline import TimelineEvent, merge_timeline, render_timeline


def _ts(s: str) -> datetime:
    return datetime.fromisoformat(s).replace(tzinfo=timezone.utc)


def test_merge_timeline_sorts_chronologically_across_sources():
    alerts = [TimelineEvent(timestamp=_ts("2026-03-04T09:31:00"), source="alert", text="resolved")]
    slack = [TimelineEvent(timestamp=_ts("2026-03-04T09:15:00"), source="slack", text="acking")]
    logs = [TimelineEvent(timestamp=_ts("2026-03-04T09:06:12"), source="log", text="timeout")]

    merged = merge_timeline(alerts, slack, logs)

    assert [e.source for e in merged] == ["log", "slack", "alert"]


def test_render_timeline_includes_source_and_timestamp():
    events = [TimelineEvent(timestamp=_ts("2026-03-04T09:06:12"), source="log", text="timeout")]
    rendered = render_timeline(events)

    assert "(log)" in rendered
    assert "2026-03-04 09:06:12 UTC" in rendered
    assert "timeout" in rendered
