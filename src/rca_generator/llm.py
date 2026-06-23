from __future__ import annotations

from typing import Protocol


class LLMClient(Protocol):
    def complete(self, system: str, prompt: str) -> str: ...


class TemplateClient:
    """Offline fallback used when no ANTHROPIC_API_KEY is configured.

    Returns a deterministic skeleton so the CLI, tests, and CI all work with
    zero network calls and zero API cost. Swap in AnthropicClient for a real
    narrative RCA.
    """

    def complete(self, system: str, prompt: str) -> str:
        return (
            "## Summary\n"
            "_(offline template output — set ANTHROPIC_API_KEY to generate a real narrative)_\n\n"
            "## Timeline\n"
            "See merged timeline above.\n\n"
            "## Impact\n"
            "Not determined (offline mode).\n\n"
            "## Root Cause\n"
            "Not determined (offline mode).\n\n"
            "## Contributing Factors\n"
            "Not determined (offline mode).\n\n"
            "## Resolution\n"
            "Not determined (offline mode).\n\n"
            "## Action Items\n"
            "- Re-run with an Anthropic API key configured for a generated analysis.\n\n"
            "## Lessons Learned\n"
            "Not determined (offline mode).\n"
        )


class AnthropicClient:
    """Real LLM-backed client. Requires the 'anthropic' extra: pip install -e .[anthropic]"""

    def __init__(self, model: str = "claude-sonnet-4-6", api_key: str | None = None):
        import anthropic  # imported lazily so the SDK isn't required in offline mode

        self._client = anthropic.Anthropic(api_key=api_key)
        self._model = model

    def complete(self, system: str, prompt: str) -> str:
        response = self._client.messages.create(
            model=self._model,
            max_tokens=2048,
            system=system,
            messages=[{"role": "user", "content": prompt}],
        )
        return "".join(block.text for block in response.content if block.type == "text")
