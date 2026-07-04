from pathlib import Path

from click.testing import CliRunner

from rca_generator.cli import main as cli_main

EXAMPLES = Path(__file__).resolve().parent.parent / "examples"


def _generate(runner, tmp_path, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    drafts = tmp_path / "drafts"
    result = runner.invoke(
        cli_main,
        ["generate", "--incident-dir", str(EXAMPLES / "incident-001"), "--drafts-dir", str(drafts)],
    )
    return result, drafts / "incident-001-rca.md"


def test_generate_writes_reviewable_draft(tmp_path, monkeypatch):
    runner = CliRunner()
    result, draft_path = _generate(runner, tmp_path, monkeypatch)

    assert result.exit_code == 0
    assert draft_path.exists()
    assert "Evidence fetched: slack, jira, monitoring, logs" in result.output
    assert "tokens:" in result.output
    draft = draft_path.read_text()
    assert "DRAFT — pending human review" in draft
    assert "## Appendix: Token Usage" in draft


def test_publish_requires_reviewer_and_gates_on_gaps(tmp_path, monkeypatch):
    runner = CliRunner()
    _, draft_path = _generate(runner, tmp_path, monkeypatch)

    # inject an unresolved gap flag, as a partial-evidence draft would contain
    draft_path.write_text(draft_path.read_text() + "\n[GAP: no monitoring data]\n")

    blocked = runner.invoke(
        cli_main,
        ["publish", str(draft_path), "--approved-by", "priya", "--published-dir", str(tmp_path / "pub")],
    )
    assert blocked.exit_code != 0
    assert "GAP" in blocked.output
    assert not (tmp_path / "pub" / draft_path.name).exists()

    acked = runner.invoke(
        cli_main,
        [
            "publish",
            str(draft_path),
            "--approved-by",
            "priya",
            "--ack-gaps",
            "--published-dir",
            str(tmp_path / "pub"),
        ],
    )
    assert acked.exit_code == 0
    published = (tmp_path / "pub" / draft_path.name).read_text()
    assert "Reviewed and approved by priya" in published
    assert "DRAFT — pending human review" not in published
