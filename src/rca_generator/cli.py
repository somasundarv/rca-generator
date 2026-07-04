from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path

import click

from .connectors import fetch_all
from .llm import AnthropicClient, TemplateClient
from .pipeline import run_pipeline
from .report import DRAFT_BANNER, render_draft


@click.group()
def main() -> None:
    """Agentic RCA generator: staged LLM pipeline with a human review gate.

    `generate` drafts the RCA (production: the /rca slash command);
    `publish` promotes a reviewed draft to the published record
    (production: Confluence review -> Google Drive).
    """


@main.command()
@click.option(
    "--incident-dir",
    required=True,
    type=click.Path(exists=True, file_okay=False),
    help="Directory with slack_thread.json, tickets.yaml, alerts.yaml, metrics_summary.yaml, logs.txt (all optional).",
)
@click.option("--name", "incident_name", default=None, help="Incident name (defaults to the directory name).")
@click.option(
    "--drafts-dir",
    type=click.Path(file_okay=False),
    default="drafts",
    show_default=True,
    help="Where the draft RCA is written for review.",
)
@click.option("--model", default="claude-sonnet-5", help="Anthropic model to use when ANTHROPIC_API_KEY is set.")
def generate(incident_dir: str, incident_name: str | None, drafts_dir: str, model: str) -> None:
    """Fetch evidence through the connectors and draft the RCA in five stages."""
    incident_name = incident_name or Path(incident_dir).name

    evidence = fetch_all(incident_dir)
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    client = AnthropicClient(model=model, api_key=api_key) if api_key else TemplateClient()

    run = run_pipeline(incident_name, evidence, client)
    draft = render_draft(run)

    out_dir = Path(drafts_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    draft_path = out_dir / f"{incident_name}-rca.md"
    draft_path.write_text(draft + "\n")

    fetched = ", ".join(name for name, ev in evidence.items() if ev.available) or "none"
    click.echo(f"Draft written to {draft_path}")
    click.echo(f"Evidence fetched: {fetched}")
    click.echo(
        f"Gaps flagged: {len(run.gaps)} | tokens: {run.ledger.total_input} in / {run.ledger.total_output} out"
    )
    if run.gaps:
        click.echo("Review the Data Gaps section before publishing.")


@main.command()
@click.argument("draft_path", type=click.Path(exists=True, dir_okay=False))
@click.option("--approved-by", required=True, help="Named reviewer signing off on the draft.")
@click.option(
    "--ack-gaps",
    is_flag=True,
    help="Publish even though the draft still contains [GAP: ...] flags.",
)
@click.option(
    "--published-dir",
    type=click.Path(file_okay=False),
    default="published",
    show_default=True,
    help="Where the approved RCA is written.",
)
def publish(draft_path: str, approved_by: str, ack_gaps: bool, published_dir: str) -> None:
    """Promote a reviewed draft to the published record (the human review gate)."""
    text = Path(draft_path).read_text()

    if "[GAP:" in text and not ack_gaps:
        raise click.ClickException(
            "Draft still contains [GAP: ...] flags. Resolve them (edit the draft after "
            "chasing the missing data) or pass --ack-gaps to publish anyway."
        )

    text = text.replace(DRAFT_BANNER + "\n", "").replace(DRAFT_BANNER, "")
    approved = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    text = text.rstrip() + f"\n\n---\n_Reviewed and approved by {approved_by} on {approved}._\n"

    out_dir = Path(published_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / Path(draft_path).name
    out_path.write_text(text)
    click.echo(f"Published to {out_path} (approved by {approved_by})")


if __name__ == "__main__":
    main()
