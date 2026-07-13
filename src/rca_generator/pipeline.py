"""Orchestrator: runs the staged, tool-using RCA pipeline over the evidence.

Mirrors the production flow (slash command -> orchestrator -> agent fetches
evidence via MCP tools -> multi-step reasoning -> draft for human review). Each
stage is an agent loop: the model calls the fetch tools it declared, observes
the results, and writes its section. File-backed connectors stand in for the
MCP servers, and the orchestrator still guarantees that a missing source is
flagged as a [GAP] rather than fabricated.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .connectors import Evidence
from .llm import LLMClient
from .stages import STAGES, Stage
from .timeline import TimelineEvent, merge_timeline, render_timeline
from .tokens import TokenLedger
from .tools import ToolBox


@dataclass
class StageResult:
    stage: Stage
    text: str
    gaps: list[str] = field(default_factory=list)
    tools_called: list[str] = field(default_factory=list)
    turns: int = 1


@dataclass
class RunResult:
    incident: str
    results: list[StageResult]
    ledger: TokenLedger
    events: list[TimelineEvent]

    @property
    def gaps(self) -> list[str]:
        return [gap for r in self.results for gap in r.gaps]

    def section(self, name: str) -> StageResult:
        return next(r for r in self.results if r.stage.name == name)


def _structural_gaps(stage: Stage, evidence: dict[str, Evidence]) -> list[str]:
    """Missing evidence becomes an explicit flag, never a fabricated section.

    Enforced by the orchestrator regardless of what the agent chose to fetch, so
    the guarantee holds even if the model skips a tool.
    """
    return [
        f"[GAP: no {name} data available — '{stage.title}' is based on partial evidence; "
        f"chase the {name} source before publishing]"
        for name in stage.tools
        if not evidence[name].available
    ]


def _build_prompt(
    incident: str,
    events: list[TimelineEvent],
    prior: list[StageResult],
    gaps: list[str],
) -> str:
    parts = [
        f"# Incident: {incident}",
        "",
        "## Merged event timeline",
        render_timeline(events),
        "",
        "Use your fetch tools to pull the underlying evidence (participants, "
        "ticket assignees, metric summaries, log detail) before writing.",
    ]
    if gaps:
        parts += ["", "## Known evidence gaps", *gaps]
    if prior:
        parts += ["", "## Sections drafted so far"]
        for r in prior:
            parts += [f"### {r.stage.title}", r.text, ""]
    return "\n".join(parts)


def run_pipeline(incident: str, evidence: dict[str, Evidence], client: LLMClient) -> RunResult:
    events = merge_timeline(*[ev.events for ev in evidence.values()])
    ledger = TokenLedger()
    toolbox = ToolBox(evidence)
    results: list[StageResult] = []

    for stage in STAGES:
        gaps = _structural_gaps(stage, evidence)
        prompt = _build_prompt(incident, events, results, gaps)
        tools = toolbox.specs(stage.tools)

        trace_start = len(toolbox.calls)
        completion = client.run_agent(stage.name, stage.system, prompt, tools, toolbox.execute)
        called = [c.name for c in toolbox.calls[trace_start:]]

        ledger.record(stage.name, completion.input_tokens, completion.output_tokens)
        results.append(
            StageResult(
                stage=stage,
                text=completion.text,
                gaps=gaps,
                tools_called=called,
                turns=completion.turns,
            )
        )

    return RunResult(incident=incident, results=results, ledger=ledger, events=events)
