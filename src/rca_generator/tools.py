"""Evidence connectors exposed as LLM tools for the agentic pipeline.

The staged pipeline used to pre-stuff every source's prose into each prompt.
Here the model *decides* what to pull: each connector is surfaced as a
`fetch_<source>` tool, and a stage's agent loop calls the tools it needs,
observes the result, and only then writes its section. A `ToolBox` binds the
tool specs to one run's already-fetched evidence, executes calls, and records a
trace (which tools ran, whether each returned data) for the draft's appendix
and for gap detection.

Tool execution reads the evidence bundle the orchestrator fetched once — the
file-backed connectors are cheap and the merged timeline needs every source —
so tools deliver the per-source *context* that is not in the timeline
(participants, ticket assignees/status, metric summaries), which is exactly what
stages like action_items and root_cause reason over.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .connectors import Evidence
from .timeline import render_timeline

# What each source's fetch tool offers the model, so it can choose deliberately.
_TOOL_DESCRIPTIONS = {
    "slack": "Fetch the incident Slack thread: channel participants and the "
    "message-by-message discussion during the incident.",
    "jira": "Fetch linked Jira tickets: keys, status, assignees, and summaries "
    "for follow-up and remediation work.",
    "monitoring": "Fetch monitoring evidence: firing alerts and the metric "
    "summary (error rates, latency, saturation) around the incident window.",
    "logs": "Fetch application/system log lines with timestamps for the "
    "affected service during the incident.",
}


def tool_name(source: str) -> str:
    return f"fetch_{source}"


def _source_of(tool: str) -> str:
    return tool[len("fetch_") :] if tool.startswith("fetch_") else tool


@dataclass
class ToolCall:
    """One tool invocation during a run: what was called and whether it hit."""

    name: str
    available: bool


@dataclass
class ToolBox:
    """Binds fetch tools to one run's evidence and records the call trace."""

    evidence: dict[str, Evidence]
    calls: list[ToolCall] = field(default_factory=list)

    def specs(self, sources: tuple[str, ...]) -> list[dict]:
        """Anthropic tool specs for the given sources, in declared order."""
        return [self._spec(source) for source in sources]

    def _spec(self, source: str) -> dict:
        return {
            "name": tool_name(source),
            "description": _TOOL_DESCRIPTIONS.get(source, f"Fetch {source} evidence."),
            "input_schema": {
                "type": "object",
                "properties": {
                    "focus": {
                        "type": "string",
                        "description": "Optional aspect to concentrate on (e.g. 'assignees', "
                        "'error rate'). The full source is returned regardless.",
                    }
                },
                "required": [],
            },
        }

    def execute(self, name: str, tool_input: dict) -> str:
        """Run a fetch tool, record the call, and return the model-facing observation."""
        source = _source_of(name)
        evidence = self.evidence.get(source)
        available = bool(evidence and evidence.available)
        self.calls.append(ToolCall(name=name, available=available))

        if not available:
            return (
                f"[GAP: no {source} data available for this incident. Do not invent "
                f"{source} details; flag the gap in your section.]"
            )

        assert evidence is not None
        parts: list[str] = []
        if evidence.context:
            parts.append(evidence.context)
        if evidence.events:
            parts += ["", "Events:", render_timeline(evidence.events)]
        return "\n".join(parts) if parts else f"{source}: source available but returned no detail."
