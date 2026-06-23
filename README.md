# rca-generator

Turns scattered incident artifacts — alert history, the Slack thread, raw
log lines, a metrics summary — into one structured, blameless postmortem.
Built on the recurring SRE problem: by the time you sit down to write the
RCA, the timeline is buried across four tools and nobody remembers the exact
sequence. This stitches it back together and hands it to an LLM to draft.

## How it works

```
alerts.yaml ─┐
slack_thread.json ─┼─► merge into one chronological timeline ─► prompt ─► LLM ─► postmortem.md
logs.txt ─┘                                                        ▲
metrics_summary.yaml (context, not timeline) ──────────────────────┘
```

1. **Sources** (`sources.py`) — parse each artifact into a common
   `TimelineEvent(timestamp, source, text)`.
2. **Timeline** (`timeline.py`) — merge all sources and sort chronologically,
   so a log line at 09:06, a Slack message at 09:15, and an alert at 09:31
   end up in one ordered narrative.
3. **Generator** (`generator.py`) — builds a prompt with a fixed RCA section
   structure (Summary, Timeline, Impact, Root Cause, Contributing Factors,
   Resolution, Action Items, Lessons Learned) and sends it to an `LLMClient`.
4. **LLM client** (`llm.py`) — pluggable. `TemplateClient` is the default and
   needs no API key (deterministic offline skeleton, used in tests/CI).
   `AnthropicClient` calls Claude for a real generated narrative once
   `ANTHROPIC_API_KEY` is set.

## Usage

```bash
pip install -e .                 # offline mode, no API key needed
rca-generator --incident-dir examples/incident-001
```

With a real LLM:

```bash
pip install -e ".[anthropic]"
export ANTHROPIC_API_KEY=sk-ant-...
rca-generator --incident-dir examples/incident-001 --output postmortem.md
```

### Example: merged timeline for `examples/incident-001`

Built automatically from `alerts.yaml` + `slack_thread.json` + `logs.txt`:

```
- [2026-03-04 09:06:12 UTC] (log) checkout-api: payment-provider request timed out after 200ms (retry 1/3)
- [2026-03-04 09:06:45 UTC] (log) checkout-api: payment-provider request timed out after 200ms (retry 2/3)
- [2026-03-04 09:07:03 UTC] (log) checkout-api: payment-provider request timed out after 200ms, giving up, returning 503
- [2026-03-04 09:12:00 UTC] (alert) [CRITICAL] CheckoutHighErrorRate on checkout-service
- [2026-03-04 09:13:00 UTC] (slack) @oncall-bot: Paging payments-team: CheckoutHighErrorRate firing on checkout-service.
- [2026-03-04 09:15:00 UTC] (slack) @priya: Acking. Checking recent deploys.
- [2026-03-04 09:19:00 UTC] (slack) @priya: Deploy at 09:05 dropped the payment-provider timeout to 200ms, way too aggressive. Rolling back.
- [2026-03-04 09:26:50 UTC] (log) checkout-api: payment-provider timeout reverted to 2000ms after rollback
- [2026-03-04 09:27:00 UTC] (slack) @priya: Rollback deployed. Error rate dropping.
- [2026-03-04 09:31:00 UTC] (alert) [RESOLVED] CheckoutHighErrorRate on checkout-service
- [2026-03-04 09:31:00 UTC] (slack) @oncall-bot: CheckoutHighErrorRate resolved on checkout-service.
```

### Example: offline output (no API key)

```
$ rca-generator --incident-dir examples/incident-001

# Postmortem: incident-001

## Summary
_(offline template output — set ANTHROPIC_API_KEY to generate a real narrative)_

## Timeline
See merged timeline above.

## Impact
Not determined (offline mode).

## Root Cause
Not determined (offline mode).

## Contributing Factors
Not determined (offline mode).

## Resolution
Not determined (offline mode).

## Action Items
- Re-run with an Anthropic API key configured for a generated analysis.

## Lessons Learned
Not determined (offline mode).
```

With `ANTHROPIC_API_KEY` set, `AnthropicClient` replaces this skeleton with
an actual root-cause narrative grounded in the timeline above (e.g. "Root
cause: the 09:05 deploy reduced the payment-provider client timeout from
2000ms to 200ms, which is below the provider's typical p99 response time...").

## Input formats

```yaml
# alerts.yaml
alerts:
  - timestamp: "2026-03-04T09:12:00Z"
    name: CheckoutHighErrorRate
    severity: critical
    service: checkout-service
```

```json
// slack_thread.json
{"messages": [{"timestamp": "2026-03-04T09:13:00Z", "user": "@oncall-bot", "text": "..."}]}
```

```
# logs.txt — "<ISO8601 timestamp> <message>" per line
2026-03-04T09:06:12Z checkout-api: payment-provider request timed out after 200ms
```

```yaml
# metrics_summary.yaml — free-form key/value context, not parsed as events
error_rate_peak: "8.7%"
incident_duration_minutes: 19
```

All four files are optional — pass whichever artifacts you actually have for
an incident.

## Development

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest
ruff check .
```

Tests run entirely offline against `TemplateClient` and the example
fixtures — no API key or network access required.

## Roadmap

- Pull alerts directly from Alertmanager's API instead of a static YAML file.
- Ingest a real Slack export (channel JSON dump) instead of the simplified
  `slack_thread.json` shape.
- Embedding-based search across past RCAs to surface similar prior incidents
  in the prompt ("this looks like INC-0042 from last quarter").

## License

MIT
