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

## Workflow (multi-step reasoning, not single-shot)

The RCA is generated in five explicit stages. Each stage is a separate LLM call
with its own scoped instruction, receives the evidence bundle plus the outputs
of prior stages, and is independently verifiable in review.

| # | Stage              | Task                                                        | Depends on |
|---|--------------------|-------------------------------------------------------------|------------|
| 1 | problem_statement  | Extract what broke, where, and the blast radius             | evidence   |
| 2 | timeline           | Narrate the incident phases over the merged event timeline  | 1          |
| 3 | root_cause         | Identify root cause + contributing factors                  | 1, 2       |
| 4 | action_items       | Compile action items with owner and SLA                     | 1–3        |
| 5 | executive_summary  | Two-paragraph summary for leadership                        | 1–4        |

Single-shot generation mixes concerns and hallucinates more; staged generation
keeps each section small, scoped, and debuggable when one section is wrong.

## Data requirements

Evidence is fetched through pluggable connectors — one per upstream system,
each behind the same interface, so adding a source is a new connector, not a
rewrite. (In the production design each connector is an MCP server; this repo
ships file-backed connectors so everything runs offline.)

| Connector  | Demo input file        | Provides                              | Required by stage |
|------------|------------------------|---------------------------------------|-------------------|
| slack      | `slack_thread.json`    | Incident-channel conversation events  | 1, 2, 4           |
| jira       | `tickets.yaml`         | Related tickets, assignees, status    | 4                 |
| monitoring | `alerts.yaml` + `metrics_summary.yaml` | Alert firings + metric context | 2, 3     |
| logs       | `logs.txt`             | Timestamped log lines                 | 3                 |

A stage whose required connector returned nothing gets a structural
`[GAP: …]` flag instead of a fabricated section.

## Output contract

One markdown document with exactly these sections, in this order: Executive
Summary, Problem Statement, Timeline, Root Cause, Action Items, Data Gaps,
Appendix: Token Usage. The document is written to `drafts/` with a DRAFT
banner; `rca-generator publish` moves it to `published/` only after a named
reviewer approves (and acknowledges any unresolved gaps).

## Quality gates

- **Gap detection** — missing evidence produces a flag, never a guess.
- **Review gate** — nothing reaches `published/` without `--approved-by`.
- **Determinism offline** — with no API key, a template client produces a
  deterministic skeleton so the CLI, tests, and CI run with zero network calls.

## Cost tracking

Every LLM call records input/output tokens into a per-run ledger, reported as
an appendix in the draft. Offline mode estimates tokens so the report shape is
identical.
