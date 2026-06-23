from pathlib import Path

from click.testing import CliRunner

from rca_generator.cli import main as cli_main
from rca_generator.generator import build_prompt, generate_postmortem
from rca_generator.llm import TemplateClient
from rca_generator.sources import load_alerts, load_logs, load_metrics_summary, load_slack_thread
from rca_generator.timeline import TimelineEvent, merge_timeline
from datetime import datetime, timezone

EXAMPLES = Path(__file__).resolve().parent.parent / "examples"


class FakeClient:
    def __init__(self):
        self.calls = []

    def complete(self, system: str, prompt: str) -> str:
        self.calls.append((system, prompt))
        return "## Summary\nFake summary.\n"


def test_build_prompt_includes_incident_name_and_timeline():
    events = [
        TimelineEvent(
            timestamp=datetime(2026, 3, 4, 9, 6, 12, tzinfo=timezone.utc),
            source="log",
            text="payment-provider timeout",
        )
    ]
    prompt = build_prompt("incident-001", events, metrics_context="- error_rate_peak: 8.7%")

    assert "# Incident: incident-001" in prompt
    assert "payment-provider timeout" in prompt
    assert "error_rate_peak: 8.7%" in prompt


def test_generate_postmortem_passes_timeline_to_client_and_wraps_header():
    events = [
        TimelineEvent(
            timestamp=datetime(2026, 3, 4, 9, 6, 12, tzinfo=timezone.utc),
            source="log",
            text="payment-provider timeout",
        )
    ]
    client = FakeClient()

    result = generate_postmortem("incident-001", events, "", client)

    assert result.startswith("# Postmortem: incident-001")
    assert "Fake summary." in result
    assert len(client.calls) == 1
    system, prompt = client.calls[0]
    assert "blameless postmortem" in system
    assert "payment-provider timeout" in prompt


def test_offline_template_client_requires_no_network():
    client = TemplateClient()
    output = client.complete(system="irrelevant", prompt="irrelevant")
    assert "## Summary" in output
    assert "## Action Items" in output


def test_example_fixtures_parse_into_expected_prompt_content():
    incident_dir = EXAMPLES / "incident-001"
    events = merge_timeline(
        load_alerts(incident_dir / "alerts.yaml"),
        load_slack_thread(incident_dir / "slack_thread.json"),
        load_logs(incident_dir / "logs.txt"),
    )
    metrics_context = load_metrics_summary(incident_dir / "metrics_summary.yaml")

    prompt = build_prompt("incident-001", events, metrics_context)

    assert "checkout-service" in prompt
    assert "payment-provider request timed out" in prompt
    assert "error_rate_peak: 8.7%" in prompt
    # chronological: first log line (09:06:12) appears before the resolution alert (09:31:00)
    assert prompt.index("09:06:12") < prompt.index("09:31:00")


def test_cli_end_to_end_offline_mode(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    runner = CliRunner()

    result = runner.invoke(cli_main, ["--incident-dir", str(EXAMPLES / "incident-001")])

    assert result.exit_code == 0
    assert "# Postmortem: incident-001" in result.output
    assert "## Summary" in result.output
    assert "## Action Items" in result.output
