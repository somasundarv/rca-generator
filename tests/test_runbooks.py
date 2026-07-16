from pathlib import Path

from click.testing import CliRunner

from rca_generator.cli import main as cli_main
from rca_generator.runbooks import apply_updates, extract_updates_section, referenced_runbooks

DRAFT = """# RCA: incident-042

## Root Cause

Connection pool exhaustion.

## Runbook Updates

Update checkout-service.md: add a "pool exhaustion" failure mode — check
`db_pool_active` in Grafana, mitigate with `kubectl rollout restart deploy/checkout`.
Also create payments-gateway.md for the gateway (no runbook exists today).
checkout-service.md should also list the new CheckoutPoolSaturation alert.

## Data Gaps

- None detected: all evidence sources were available.
"""


def test_extract_and_reference_parsing():
    section = extract_updates_section(DRAFT)
    assert section is not None
    assert section.startswith("Update checkout-service.md")
    assert "Data Gaps" not in section
    # deduped, first-mention order
    assert referenced_runbooks(section) == ["checkout-service.md", "payments-gateway.md"]
    assert extract_updates_section("# RCA\n\n## Root Cause\n\nx\n") is None


def test_apply_updates_appends_learnings_and_reports_missing(tmp_path):
    runbook = tmp_path / "checkout-service.md"
    runbook.write_text("# Runbook: checkout-service\n\n## Alerts\n")

    updated, missing = apply_updates(DRAFT, tmp_path, "incident-042", "priya")

    assert updated == [runbook]
    assert missing == ["payments-gateway.md"]
    text = runbook.read_text()
    assert "## Learnings from incident-042" in text
    assert "reviewer: priya" in text
    assert "pool exhaustion" in text
    # original content intact, learnings appended once at the end
    assert text.startswith("# Runbook: checkout-service")
    assert text.count("## Learnings from") == 1


def test_publish_update_runbooks_flag(tmp_path):
    drafts = tmp_path / "drafts"
    drafts.mkdir()
    draft_path = drafts / "incident-042-rca.md"
    draft_path.write_text(DRAFT)
    runbooks_dir = tmp_path / "runbooks"
    runbooks_dir.mkdir()
    (runbooks_dir / "checkout-service.md").write_text("# Runbook: checkout-service\n")

    result = CliRunner().invoke(
        cli_main,
        [
            "publish",
            str(draft_path),
            "--approved-by",
            "priya",
            "--published-dir",
            str(tmp_path / "pub"),
            "--update-runbooks",
            str(runbooks_dir),
        ],
    )

    assert result.exit_code == 0, result.output
    assert "Runbook updated:" in result.output
    assert "payments-gateway.md" in result.output  # flagged as needing manual creation
    assert "## Learnings from incident-042" in (runbooks_dir / "checkout-service.md").read_text()


def test_example_runbook_fixture_exists():
    examples = Path(__file__).resolve().parent.parent / "examples"
    assert (examples / "incident-001" / "runbooks" / "checkout-service.md").is_file()
