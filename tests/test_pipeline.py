from pathlib import Path

from rca_generator.connectors import Evidence, fetch_all
from rca_generator.llm import Completion, TemplateClient
from rca_generator.pipeline import run_pipeline
from rca_generator.report import render_draft
from rca_generator.stages import STAGES

EXAMPLES = Path(__file__).resolve().parent.parent / "examples"


class RecordingClient:
    def __init__(self):
        self.calls = []

    def complete(self, stage: str, system: str, prompt: str) -> Completion:
        self.calls.append((stage, system, prompt))
        return Completion(text=f"generated {stage}", input_tokens=100, output_tokens=10)


def test_pipeline_runs_all_stages_in_order_with_prior_context():
    evidence = fetch_all(EXAMPLES / "incident-001")
    client = RecordingClient()

    run = run_pipeline("incident-001", evidence, client)

    assert [name for name, _, _ in client.calls] == [s.name for s in STAGES]
    # each stage after the first sees the sections drafted so far
    _, _, root_cause_prompt = client.calls[2]
    assert "generated problem_statement" in root_cause_prompt
    assert "generated timeline" in root_cause_prompt
    # final stage synthesizes from all four prior sections
    _, _, summary_prompt = client.calls[4]
    assert "generated action_items" in summary_prompt
    # full evidence bundle -> no structural gaps
    assert run.gaps == []
    assert len(run.ledger.entries) == len(STAGES)
    assert run.ledger.total_input == 100 * len(STAGES)


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
    ]
    positions = [draft.index(h) for h in expected_order]
    assert positions == sorted(positions)
    assert "DRAFT — pending human review" in draft
    # chronological merged timeline: first log line before resolution alert
    assert draft.index("09:06:12") < draft.index("09:31:00")


def test_stage_requirements_reference_real_connectors():
    evidence = fetch_all(EXAMPLES / "incident-001")
    for stage in STAGES:
        for name in stage.requires:
            assert name in evidence, f"{stage.name} requires unknown connector {name}"


def test_evidence_dataclass_defaults():
    ev = Evidence(source="grafana", available=False)
    assert ev.events == [] and ev.context == ""
