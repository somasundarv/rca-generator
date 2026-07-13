from pathlib import Path

from rca_generator.connectors import Evidence, fetch_all
from rca_generator.llm import Completion, TemplateClient, ToolExecutor
from rca_generator.pipeline import run_pipeline
from rca_generator.report import render_draft
from rca_generator.stages import STAGES

EXAMPLES = Path(__file__).resolve().parent.parent / "examples"


class RecordingClient:
    """Fake agent: exercises the real tool executor, records prompts + tool names."""

    def __init__(self):
        self.calls = []  # (stage, system, prompt, tool_names)

    def run_agent(
        self,
        stage: str,
        system: str,
        prompt: str,
        tools: list[dict],
        execute: ToolExecutor,
        max_turns: int = 6,
    ) -> Completion:
        tool_names = [t["name"] for t in tools]
        for name in tool_names:  # drive the toolbox so the trace + gaps populate
            execute(name, {})
        self.calls.append((stage, system, prompt, tool_names))
        return Completion(text=f"generated {stage}", input_tokens=100, output_tokens=10, turns=1)


def test_pipeline_runs_all_stages_in_order_with_prior_context():
    evidence = fetch_all(EXAMPLES / "incident-001")
    client = RecordingClient()

    run = run_pipeline("incident-001", evidence, client)

    assert [name for name, _, _, _ in client.calls] == [s.name for s in STAGES]
    # each stage after the first sees the sections drafted so far
    _, _, root_cause_prompt, _ = client.calls[2]
    assert "generated problem_statement" in root_cause_prompt
    assert "generated timeline" in root_cause_prompt
    # final stage synthesizes from all four prior sections
    _, _, summary_prompt, _ = client.calls[4]
    assert "generated action_items" in summary_prompt
    # full evidence bundle -> no structural gaps
    assert run.gaps == []
    assert len(run.ledger.entries) == len(STAGES)
    assert run.ledger.total_input == 100 * len(STAGES)


def test_stages_call_their_declared_fetch_tools():
    evidence = fetch_all(EXAMPLES / "incident-001")
    run = run_pipeline("incident-001", evidence, RecordingClient())

    assert run.section("problem_statement").tools_called == ["fetch_slack"]
    assert run.section("root_cause").tools_called == ["fetch_monitoring", "fetch_logs"]
    # executive summary declares no tools
    assert run.section("executive_summary").tools_called == []
    # the trace surfaces in the draft appendix
    draft = render_draft(run)
    assert "## Appendix: Agent Trace" in draft
    assert "fetch_monitoring, fetch_logs" in draft


def test_missing_evidence_is_flagged_never_fabricated(tmp_path):
    # copy only the slack thread: monitoring, logs, and jira are absent
    thread = (EXAMPLES / "incident-001" / "slack_thread.json").read_text()
    (tmp_path / "slack_thread.json").write_text(thread)

    run = run_pipeline("incident-x", fetch_all(tmp_path), TemplateClient())

    assert any("no monitoring data" in gap for gap in run.gaps)
    assert any("no logs data" in gap for gap in run.gaps)
    root_cause = run.section("root_cause")
    assert len(root_cause.gaps) == 2  # monitoring + logs both missing for this stage
    draft = render_draft(run)
    assert "[GAP:" in draft
    assert "## Data Gaps" in draft


def test_connectors_registry_reads_example_bundle():
    evidence = fetch_all(EXAMPLES / "incident-001")

    assert set(evidence) == {"slack", "jira", "monitoring", "logs"}
    assert all(ev.available for ev in evidence.values())
    assert any("OPS-4312" in e.text for e in evidence["jira"].events)
    assert "error_rate_peak" in evidence["monitoring"].context


def test_draft_follows_output_contract_offline():
    run = run_pipeline("incident-001", fetch_all(EXAMPLES / "incident-001"), TemplateClient())
    draft = render_draft(run)

    expected_order = [
        "## Executive Summary",
        "## Problem Statement",
        "## Timeline",
        "## Root Cause",
        "## Action Items",
        "## Data Gaps",
        "## Appendix: Token Usage",
        "## Appendix: Agent Trace",
    ]
    positions = [draft.index(h) for h in expected_order]
    assert positions == sorted(positions)
    assert "DRAFT — pending human review" in draft
    # chronological merged timeline: first log line before resolution alert
    assert draft.index("09:06:12") < draft.index("09:31:00")


def test_stage_tools_reference_real_connectors():
    evidence = fetch_all(EXAMPLES / "incident-001")
    for stage in STAGES:
        for name in stage.tools:
            assert name in evidence, f"{stage.name} declares unknown connector {name}"


def test_evidence_dataclass_defaults():
    ev = Evidence(source="grafana", available=False)
    assert ev.events == [] and ev.context == ""
