from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class TokenLedger:
    """Per-stage token accounting for one pipeline run.

    Cost awareness from day one: every LLM call is recorded here and reported
    as an appendix in the draft, so expensive stages are visible per run
    rather than discovered on the monthly bill.
    """

    entries: list[tuple[str, int, int]] = field(default_factory=list)

    def record(self, stage: str, input_tokens: int, output_tokens: int) -> None:
        self.entries.append((stage, input_tokens, output_tokens))

    @property
    def total_input(self) -> int:
        return sum(i for _, i, _ in self.entries)

    @property
    def total_output(self) -> int:
        return sum(o for _, _, o in self.entries)

    def render(self) -> str:
        lines = ["| Stage | Input tokens | Output tokens |", "|---|---|---|"]
        for stage, i, o in self.entries:
            lines.append(f"| {stage} | {i} | {o} |")
        lines.append(f"| **total** | **{self.total_input}** | **{self.total_output}** |")
        return "\n".join(lines)
