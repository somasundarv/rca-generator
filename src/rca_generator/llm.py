from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass
class Completion:
    text: str
    input_tokens: int
    output_tokens: int


class LLMClient(Protocol):
    def complete(self, stage: str, system: str, prompt: str) -> Completion: ...


def estimate_tokens(text: str) -> int:
    """Rough offline estimate (~4 chars/token) so the ledger works without an API."""
    return max(len(text) // 4, 1)


_OFFLINE_NOTE = "_(offline template output — set ANTHROPIC_API_KEY for a generated draft)_"

_TEMPLATES = {
    "problem_statement": "What broke, where, and the blast radius: not determined in offline mode.",
    "timeline": "See the merged event timeline above. Phase narration requires an LLM.",
    "root_cause": "Root cause and contributing factors: not determined in offline mode.",
    "action_items": "| Action | Owner | SLA |\n|---|---|---|\n| Re-run with an API key configured | - | - |",
    "executive_summary": "Executive summary: not generated in offline mode.",
}


class TemplateClient:
    """Offline fallback used when no ANTHROPIC_API_KEY is configured.

    Returns a deterministic per-stage skeleton so the CLI, tests, and CI all
    exercise the full multi-stage pipeline with zero network calls and zero
    API cost. Swap in AnthropicClient for a real narrative RCA.
    """

    def complete(self, stage: str, system: str, prompt: str) -> Completion:
        body = _TEMPLATES.get(stage, "Not determined (offline mode).")
        text = f"{_OFFLINE_NOTE}\n\n{body}"
        return Completion(
            text=text,
            input_tokens=estimate_tokens(system) + estimate_tokens(prompt),
            output_tokens=estimate_tokens(text),
        )


class AnthropicClient:
    """Real LLM-backed client. Requires the 'anthropic' extra: pip install -e .[anthropic]"""

    def __init__(self, model: str = "claude-sonnet-5", api_key: str | None = None):
        import anthropic  # imported lazily so the SDK isn't required in offline mode

        self._client = anthropic.Anthropic(api_key=api_key)
        self._model = model

    def complete(self, stage: str, system: str, prompt: str) -> Completion:
        response = self._client.messages.create(
            model=self._model,
            max_tokens=4096,
            system=system,
            messages=[{"role": "user", "content": prompt}],
        )
        text = "".join(block.text for block in response.content if block.type == "text")
        return Completion(
            text=text,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
        )
