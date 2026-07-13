# RCA Generator — Agent Specification

This project is built spec-first: the agent's problem statement, goals, workflow,
and data requirements are pinned down here before any prompt or code. The
pipeline in `src/rca_generator/` implements this spec; behavior not described
here is out of scope for the agent.

## Problem statement

After a P1 incident, writing the RCA takes engineers 24–48 hours: scanning the
Slack incident channel, chasing teams for ticket references and monitoring
data, and hand-assembling everything into the standard postmortem format. The
information already exists — it is just scattered across tools.

## Goals

1. Produce a fully structured RCA draft in minutes from the incident's existing
   artifacts (Slack thread, tickets, monitoring data, logs).
2. Follow the standard RCA template exactly, every time — consistent documents,
   no format drift.
3. Never fabricate: when the evidence for a section is missing or thin, flag the
   gap explicitly so engineers know what to chase.
4. Keep a human review gate between the generated draft and the published
   record.
5. Track token usage per run, per stage — cost awareness from day one.

## Non-goals

- Automated remediation or paging. This agent writes documents.
- Replacing human judgment on root cause. The draft is a starting point that is
  reviewed, corrected, and only then published.

## Workflow (agentic, staged — not single-shot)

The RCA is generated in five explicit stages. Each stage is its own tool-use
agent loop: with a scoped instruction, it calls the fetch tools it declared to
pull the evidence it needs, observes the results, and only then writes its
section — receiving the merged event timeline plus the outputs of prior stages.
Each section is independently verifiable in review.

| # | Stage              | Task                                                        | Prior deps | Fetch tools        |
|---|--------------------|-------------------------------------------------------------|------------|--------------------|
| 1 | problem_statement  | Extract what broke, where, and the blast radius             | —          | slack              |
| 2 | timeline           | Narrate the incident phases over the merged event timeline  | 1          | slack, monitoring  |
| 3 | root_cause         | Identify root cause + contributing factors                  | 1, 2       | monitoring, logs   |
| 4 | action_items       | Compile action items with owner and SLA                     | 1–3        | slack, jira        |
| 5 | executive_summary  | Two-paragraph summary for leadership                        | 1–4        | — (synthesis only) |

Single-shot generation mixes concerns and hallucinates more; staged, tool-grounded
generation keeps each section small, scoped, evidence-backed, and debuggable when
one section is wrong. The tools a stage called and the turns it took are recorded
in the draft's Agent Trace appendix.

## Data requirements

Evidence is fetched through pluggable connectors — one per upstream system,
each behind the same interface and each surfaced to the model as a
`fetch_<source>` tool, so adding a source is a new connector, not a rewrite.
(In the production design each connector is an MCP server; this repo ships
file-backed connectors so everything runs offline.)

| Connector  | Demo input file        | Provides                              | Fetched by stage |
|------------|------------------------|---------------------------------------|------------------|
| slack      | `slack_thread.json`    | Incident-channel conversation events  | 1, 2, 4          |
| jira       | `tickets.yaml`         | Related tickets, assignees, status    | 4                |
| monitoring | `alerts.yaml` + `metrics_summary.yaml` | Alert firings + metric context | 2, 3    |
| logs       | `logs.txt`             | Timestamped log lines                 | 3                |

Two-layer gap handling: a `fetch_<source>` tool that hits an absent source
returns a `[GAP: …]` observation instead of data, and the orchestrator
additionally emits a structural `[GAP: …]` flag for any declared-but-missing
source regardless of what the agent chose to fetch — so a missing source is
never a fabricated section.

## Output contract

One markdown document with exactly these sections, in this order: Executive
Summary, Problem Statement, Timeline, Root Cause, Action Items, Data Gaps,
Appendix: Token Usage, Appendix: Agent Trace. The document is written to
`drafts/` with a DRAFT banner; `rca-generator publish` moves it to `published/`
only after a named reviewer approves (and acknowledges any unresolved gaps).

## Quality gates

- **Gap detection** — missing evidence produces a flag, never a guess.
- **Review gate** — nothing reaches `published/` without `--approved-by`.
- **Determinism offline** — with no API key, a template client fakes the agent
  (calling every declared tool through the real executor, then emitting a
  deterministic skeleton) so the CLI, tests, and CI exercise the full tool
  plumbing with zero network calls.

## Cost tracking

Each stage's agent loop records input/output tokens — summed across every tool
turn — into a per-run ledger, reported as an appendix in the draft alongside
the Agent Trace. Offline mode estimates tokens so the report shape is identical.
