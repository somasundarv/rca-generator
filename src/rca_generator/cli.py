from __future__ import annotations

import os
from pathlib import Path

import click

from .generator import generate_postmortem
from .llm import AnthropicClient, TemplateClient
from .sources import load_alerts, load_logs, load_metrics_summary, load_slack_thread
from .timeline import merge_timeline


@click.command()
@click.option(
    "--incident-dir",
    required=True,
    type=click.Path(exists=True, file_okay=False),
    help="Directory containing alerts.yaml, slack_thread.json, logs.txt, metrics_summary.yaml (all optional).",
)
@click.option("--name", "incident_name", default=None, help="Incident name (defaults to the directory name).")
@click.option(
    "--output",
    "output_path",
    type=click.Path(),
    default=None,
    help="Write postmortem markdown to this file instead of stdout.",
)
@click.option("--model", default="claude-sonnet-4-6", help="Anthropic model to use when ANTHROPIC_API_KEY is set.")
def main(incident_dir: str, incident_name: str | None, output_path: str | None, model: str) -> None:
    """Generate a structured RCA/postmortem from incident alerts, a Slack export, logs, and metrics."""
    incident_path = Path(incident_dir)
    incident_name = incident_name or incident_path.name

    alerts_file = incident_path / "alerts.yaml"
    slack_file = incident_path / "slack_thread.json"
    logs_file = incident_path / "logs.txt"
    metrics_file = incident_path / "metrics_summary.yaml"

    events = merge_timeline(
        load_alerts(alerts_file) if alerts_file.exists() else [],
        load_slack_thread(slack_file) if slack_file.exists() else [],
        load_logs(logs_file) if logs_file.exists() else [],
    )
    metrics_context = load_metrics_summary(metrics_file) if metrics_file.exists() else ""

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    client = AnthropicClient(model=model, api_key=api_key) if api_key else TemplateClient()

    postmortem = generate_postmortem(incident_name, events, metrics_context, client)

    if output_path:
        Path(output_path).write_text(postmortem + "\n")
    else:
        click.echo(postmortem)


if __name__ == "__main__":
    main()
