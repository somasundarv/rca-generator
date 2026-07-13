"""The five reasoning stages of the RCA pipeline.

Each stage is a separate, scoped agent rather than one mega-prompt: single-shot
generation mixes concerns and hallucinates more, while staged generation keeps
every section small, independently verifiable in review, and easy to debug when
one section comes out wrong. `tools` names the evidence connectors a stage may
call — the stage runs a tool-use loop, pulling exactly those sources on demand,
and turns a missing source into an explicit [GAP] flag instead of guessing.
"""

from __future__ import annotations

from dataclasses import dataclass

_BLAMELESS = (
    "You are an SRE writing one section of a blameless postmortem. Before you "
    "write, call your fetch tools to pull the evidence you need for this "
    "section — do not rely on memory or assume evidence you have not fetched. "
    "Cite timestamps from the evidence, label any speculation clearly, never "
    "assign blame to individuals, and if a tool reports no data or the evidence "
    "is insufficient for a claim, write '[GAP: <what data is missing>]' instead "
    "of inventing it. Once you have gathered enough evidence, write only this "
    "section's prose (no tool chatter). "
)


@dataclass(frozen=True)
class Stage:
    name: str
    title: str
    tools: tuple[str, ...]  # connector names this stage may fetch via tools
    system: str


STAGES: tuple[Stage, ...] = (
    Stage(
        name="problem_statement",
        title="Problem Statement",
        tools=("slack",),
        system=_BLAMELESS
        + "Task: state what broke, where, when it started, and the customer/"
        "business blast radius. 3-5 sentences, no root-cause analysis yet.",
    ),
    Stage(
        name="timeline",
        title="Timeline",
        tools=("slack", "monitoring"),
        system=_BLAMELESS
        + "Task: narrate the incident phases (detection, escalation, diagnosis, "
        "mitigation, resolution) over the merged event timeline provided. "
        "Reference concrete events and timestamps; do not restate every event.",
    ),
    Stage(
        name="root_cause",
        title="Root Cause",
        tools=("monitoring", "logs"),
        system=_BLAMELESS
        + "Task: identify the root cause and contributing factors. Distinguish "
        "trigger from underlying cause. If monitoring or log evidence is thin, "
        "present the conclusion as a hypothesis derived from conversation only "
        "and flag the gap.",
    ),
    Stage(
        name="action_items",
        title="Action Items",
        tools=("slack", "jira"),
        system=_BLAMELESS
        + "Task: compile action items as a markdown table with columns Action, "
        "Owner, SLA. Derive owners from incident participants and ticket "
        "assignees; use existing ticket keys where they cover an action.",
    ),
    Stage(
        name="executive_summary",
        title="Executive Summary",
        tools=(),
        system=_BLAMELESS
        + "Task: write a two-paragraph executive summary for leadership from "
        "the prior sections: what happened and the impact, then the root cause "
        "and what is being done. No jargon, no timeline dump. (No tools needed; "
        "synthesize the sections drafted so far.)",
    ),
)
