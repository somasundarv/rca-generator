"""Apply an approved RCA's proposed runbook edits to the runbook files.

The runbook_updates stage proposes edits and references each affected runbook
by exact filename; this module is the deterministic other half. It only runs
from `publish --update-runbooks`, i.e. behind the human review gate: a
reviewer has read (and possibly corrected) the proposals before any runbook
changes. Learnings are appended as a dated, incident-linked section rather
than edited inline, so the runbook's own history stays reviewable in git.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path

_SECTION_HEADER = "## Runbook Updates"
_FILENAME_RE = re.compile(r"\b([\w][\w.-]*\.md)\b")


def extract_updates_section(draft: str) -> str | None:
    """Return the Runbook Updates section body, or None if the draft lacks one."""
    start = draft.find(_SECTION_HEADER)
    if start == -1:
        return None
    body_start = start + len(_SECTION_HEADER)
    next_section = draft.find("\n## ", body_start)
    body = draft[body_start : next_section if next_section != -1 else None]
    return body.strip() or None


def referenced_runbooks(section: str) -> list[str]:
    """Runbook filenames the section references, in first-mention order."""
    seen: list[str] = []
    for name in _FILENAME_RE.findall(section):
        if name not in seen:
            seen.append(name)
    return seen


def apply_updates(
    draft: str, runbooks_dir: str | Path, incident: str, approved_by: str
) -> tuple[list[Path], list[str]]:
    """Append the approved learnings to each referenced runbook.

    Returns (updated paths, filenames referenced but not found on disk —
    typically proposals for brand-new runbooks, left for a human to create).
    """
    section = extract_updates_section(draft)
    if section is None:
        return [], []

    runbooks_dir = Path(runbooks_dir)
    date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    block = (
        f"\n\n## Learnings from {incident} ({date})\n\n"
        f"_Appended from the approved RCA (reviewer: {approved_by})._\n\n"
        f"{section}\n"
    )

    updated: list[Path] = []
    missing: list[str] = []
    for name in referenced_runbooks(section):
        path = runbooks_dir / name
        if not path.is_file():
            missing.append(name)
            continue
        path.write_text(path.read_text().rstrip() + block)
        updated.append(path)
    return updated, missing
