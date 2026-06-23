from __future__ import annotations

from .llm import LLMClient
from .timeline import TimelineEvent, render_timeline

SYSTEM_PROMPT = (
    "You are an SRE writing a blameless postmortem. Given an incident timeline "
    "merged from alerts, Slack discussion, and logs, produce a structured RCA "
    "in markdown with these exact sections: Summary, Timeline, Impact, Root "
    "Cause, Contributing Factors, Resolution, Action Items, Lessons Learned. "
    "Be specific, cite timestamps from the timeline, and keep speculation "
    "clearly labeled as such. Do not assign blame to individuals."
)


def build_prompt(incident_name: str, events: list[TimelineEvent], metrics_context: str) -> str:
    parts = [f"# Incident: {incident_name}", "", "## Raw merged timeline", render_timeline(events)]
    if metrics_context:
        parts += ["", "## Metrics context", metrics_context]
    return "\n".join(parts)


def generate_postmortem(
    incident_name: str,
    events: list[TimelineEvent],
    metrics_context: str,
    client: LLMClient,
) -> str:
    prompt = build_prompt(incident_name, events, metrics_context)
    body = client.complete(SYSTEM_PROMPT, prompt)
    return f"# Postmortem: {incident_name}\n\n{body}"
