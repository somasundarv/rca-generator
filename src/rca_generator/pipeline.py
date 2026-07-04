"""Orchestrator: runs the staged RCA pipeline over the evidence bundle.

Mirrors the production flow (slash command -> orchestrator -> MCP fetches ->
multi-step reasoning -> draft for human review) with file-backed connectors
standing in for the MCP servers.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .connectors import Evidence
from .llm import LLMClient
from .stages import STAGES, Stage
from .timeline import TimelineEvent, merge_timeline, render_timeline
from .tokens import TokenLedger


@dataclass
class StageResult:
    stage: Stage
    text: str
    gaps: list[str] = field(default_factory=list)


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
    """Missing evidence becomes an explicit flag, never a fabricated section."""
    return [
        f"[GAP: no {name} data available — '{stage.title}' is based on partial evidence; "
        f"chase the {name} source before publishing]"
        for name in stage.requires
        if not evidence[name].available
    ]


def _build_prompt(
    incident: str,
    evidence: dict[str, Evidence],
    events: list[TimelineEvent],
    prior: list[StageResult],
    gaps: list[str],
) -> str:
    parts = [f"# Incident: {incident}", "", "## Merged event timeline", render_timeline(events)]
    for ev in evidence.values():
        if ev.available and ev.context:
            parts += ["", f"## Evidence: {ev.source}", ev.context]
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
    results: list[StageResult] = []

    for stage in STAGES:
        gaps = _structural_gaps(stage, evidence)
        prompt = _build_prompt(incident, evidence, events, results, gaps)
        completion = client.complete(stage.name, stage.system, prompt)
        ledger.record(stage.name, completion.input_tokens, completion.output_tokens)
        results.append(StageResult(stage=stage, text=completion.text, gaps=gaps))

    return RunResult(incident=incident, results=results, ledger=ledger, events=events)
