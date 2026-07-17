# rca-generator

![CI](https://github.com/somasundarv/rca-generator/actions/workflows/ci.yml/badge.svg)

An agentic RCA generator. After a P1 incident, writing the postmortem takes
engineers a day or two: scanning the Slack incident channel, chasing teams for
ticket references and monitoring data, and hand-assembling it all into the
standard format. This collapses that to minutes — a staged LLM pipeline pulls
the incident's existing artifacts through pluggable connectors, reasons over
them in six verifiable steps, and produces a fully structured RCA draft that a
human reviews before it becomes the record — including proposed runbook edits
that, once approved, are applied back to the runbooks so the next on-call
benefits from the incident.

Built spec-first: [SPEC.md](SPEC.md) pins down the problem statement, goals,
workflow stages, and data requirements the pipeline implements. Behavior not
in the spec is out of scope for the agent — that's what keeps it predictable
rather than open-ended.

## Architecture

```mermaid
flowchart TD
    A["Slack incident channel<br/>/rca slash command<br/><i>(demo: rca-generator generate)</i>"] --> B["Orchestrator<br/>spec-driven staged workflow"]
    B --> C1["Connector: slack<br/>chat history"]
    B --> C2["Connector: jira<br/>related tickets"]
    B --> C3["Connector: monitoring<br/>alerts + metrics"]
    B --> C4["Connector: logs<br/>timestamped lines"]
    B --> C5["Connector: runbooks<br/>per-service runbooks"]
    C1 & C2 & C3 & C4 & C5 --> D["Evidence bundle<br/>+ merged event timeline"]
    D --> E["Per-stage agent loops<br/>each fetches evidence via tools,<br/>then writes: problem → timeline →<br/>root cause → actions → runbook edits → summary"]
    E --> F["Structured RCA draft<br/>+ gap flags + token ledger"]
    F --> G{"Human review gate"}
    G -->|approve| H["Published record<br/><i>(production: Confluence review → Google Drive)</i>"]
    G -->|"approve + --update-runbooks"| I["Runbooks updated<br/>dated learnings block appended"]
    I -.->|next incident reads<br/>smarter runbooks| C5
```

Production deploys this as a Slack bot: the slash command invokes the
workflow, each connector is an MCP server, the draft lands in Confluence for
review, and the approved document ships to Google Drive. This repo is the
same pipeline with file-backed stand-ins so everything runs offline:

| Production                     | This repo                                      |
|--------------------------------|------------------------------------------------|
| `/rca` slash command           | `rca-generator generate --incident-dir …`      |
| MCP servers (Slack/Jira/Grafana/logs) | File-backed connectors behind the same protocol (`connectors.py`) |
| Claude via Bedrock             | Anthropic API, or a deterministic offline template client |
| Confluence draft for review    | `drafts/`                                      |
| Google Drive published record  | `rca-generator publish` → `published/`         |

## Design decisions

- **Pluggable connectors, exposed as tools (MCP in production)** — the
  orchestrator only sees the `Connector` protocol, and each connector is
  surfaced to the model as a `fetch_<source>` tool (`tools.py`). Adding Grafana
  or Sumo Logic is a new registry entry, not a rewrite. Loose coupling is the
  point.
- **Agentic, not single-shot** — six scoped stages (`stages.py`), each a
  tool-use agent loop (`llm.py`): the stage calls the fetch tools it declared,
  observes the evidence, and only then writes its section, receiving the merged
  timeline plus prior sections. The model pulls evidence on demand rather than
  having every source pre-stuffed into one mega-prompt. Smaller, tool-grounded
  prompts hallucinate less, and each section is independently verifiable — when
  one is wrong, you debug one stage. The tools each stage called and the turns
  it took are recorded in the draft's Agent Trace appendix.
- **Gap detection over fabrication** — a stage whose declared evidence is
  missing gets a structural `[GAP: …]` flag (orchestrator-enforced regardless
  of what the agent chose to fetch, not prompt-hoped), and a fetch tool that
  hits an absent source returns a `[GAP: …]` observation instead of data.
  Engineers see exactly what to chase.
- **Human review gate** — `generate` only ever writes a DRAFT.
  `publish --approved-by <name>` promotes it, and refuses while unresolved
  `[GAP:]` flags remain unless explicitly acknowledged. Bad RCAs stay out of
  the record.
- **Token ledger** — every stage's input/output tokens are recorded per run
  and reported in the draft's appendix. Cost awareness from day one.
- **Runbooks learn from every incident** — the runbook_updates stage reads the
  existing runbooks and proposes concrete edits (detection signals, diagnosis
  steps, the mitigation that actually worked), referencing each runbook by
  filename. `publish --update-runbooks <dir>` applies the approved section to
  each referenced runbook as a dated learnings block — after human review,
  never at draft time (`runbooks.py`). The RCA improves the docs the next
  on-call will actually use.

## Usage

```bash
pip install -e .

# 1. Draft (offline template mode; set ANTHROPIC_API_KEY for a real narrative)
rca-generator generate --incident-dir examples/incident-001

# 2. Review drafts/incident-001-rca.md, resolve gaps, then publish —
#    optionally applying the approved runbook edits back to the runbooks
rca-generator publish drafts/incident-001-rca.md --approved-by priya \
  --update-runbooks examples/incident-001/runbooks
```

`generate` prints a run summary:

```
Draft written to drafts/incident-001-rca.md
Evidence fetched: slack, jira, monitoring, logs, runbooks
Gaps flagged: 0 | tokens: 5337 in / 209 out
```

Point it at a directory containing only the Slack thread and the same run
flags what's missing instead of guessing:

```
Evidence fetched: slack
Gaps flagged: 6 | tokens: 3713 in / 209 out
Review the Data Gaps section before publishing.
```

With `ANTHROPIC_API_KEY` set, each stage runs as a real tool-use loop against
the Anthropic API (`--model`, default `claude-sonnet-5`); without it, a
deterministic template client fakes the agent — it still calls every declared
tool through the real executor, so CI exercises the identical pipeline offline
(same stages, same tool plumbing, same gap flags, same ledger and trace).
One offline caveat: the template's Runbook Updates section references no
runbook filenames, so `publish --update-runbooks` reports "nothing applied" —
expected; LLM-drafted RCAs reference runbooks by filename and do get applied.

## Input formats

An incident directory holds whatever artifacts exist (all optional — missing
ones become gap flags): `slack_thread.json`, `tickets.yaml`, `alerts.yaml`,
`metrics_summary.yaml`, `logs.txt`, and a `runbooks/` directory of per-service
markdown runbooks. See `examples/incident-001/` for the shapes.

## Limitations

Root-cause accuracy is bounded by evidence completeness: Slack and tickets
capture what people *said*, not what the system *did*. When monitoring and
log data are absent the pipeline says so instead of guessing — but a flagged
gap is still a gap. The roadmap is more telemetry connectors (full Grafana
metric history, Sumo Logic queries, deployment history) so the reasoning
moves from summarizing the conversation to diagnosing the system.

## Development

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest
ruff check .
```

## License

MIT
