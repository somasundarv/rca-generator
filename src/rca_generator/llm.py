from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Protocol

# Executes a tool call: (tool_name, tool_input) -> observation string.
ToolExecutor = Callable[[str, dict], str]


@dataclass
class Completion:
    text: str
    input_tokens: int
    output_tokens: int
    turns: int = 1  # model round-trips taken (>1 when tools were called)


class LLMClient(Protocol):
    def run_agent(
        self,
        stage: str,
        system: str,
        prompt: str,
        tools: list[dict],
        execute: ToolExecutor,
        max_turns: int = 6,
    ) -> Completion: ...


def estimate_tokens(text: str) -> int:
    """Rough offline estimate (~4 chars/token) so the ledger works without an API."""
    return max(len(text) // 4, 1)


_OFFLINE_NOTE = "_(offline template output — set ANTHROPIC_API_KEY for a generated draft)_"

_TEMPLATES = {
    "problem_statement": "What broke, where, and the blast radius: not determined in offline mode.",
    "timeline": "See the merged event timeline above. Phase narration requires an LLM.",
    "root_cause": "Root cause and contributing factors: not determined in offline mode.",
    "action_items": "| Action | Owner | SLA |\n|---|---|---|\n| Re-run with an API key configured | - | - |",
    "runbook_updates": "Proposed runbook edits: not determined in offline mode.",
    "executive_summary": "Executive summary: not generated in offline mode.",
}


class TemplateClient:
    """Offline fallback used when no ANTHROPIC_API_KEY is configured.

    Fakes the agent: for each stage it calls every declared tool once, in a
    fixed order, against the file-backed connectors, then emits a deterministic
    per-stage skeleton. Only the *tool-choosing* is scripted — the tool
    execution path (fetch, observe, gap-flag, trace) is the real one, so the
    CLI, tests, and CI exercise the full agentic plumbing with zero network
    calls and zero API cost. Swap in AnthropicClient for a real narrative RCA.
    """

    def run_agent(
        self,
        stage: str,
        system: str,
        prompt: str,
        tools: list[dict],
        execute: ToolExecutor,
        max_turns: int = 6,
    ) -> Completion:
        input_tokens = estimate_tokens(system) + estimate_tokens(prompt)
        for spec in tools:  # deterministic: pull every declared source, in order
            observation = execute(spec["name"], {})
            input_tokens += estimate_tokens(observation)

        body = _TEMPLATES.get(stage, "Not determined (offline mode).")
        text = f"{_OFFLINE_NOTE}\n\n{body}"
        return Completion(
            text=text,
            input_tokens=input_tokens,
            output_tokens=estimate_tokens(text),
            turns=2 if tools else 1,
        )


class AnthropicClient:
    """Real LLM-backed client. Requires the 'anthropic' extra: pip install -e .[anthropic]"""

    def __init__(self, model: str = "claude-sonnet-5", api_key: str | None = None):
        import anthropic  # imported lazily so the SDK isn't required in offline mode

        self._client = anthropic.Anthropic(api_key=api_key)
        self._model = model

    def run_agent(
        self,
        stage: str,
        system: str,
        prompt: str,
        tools: list[dict],
        execute: ToolExecutor,
        max_turns: int = 6,
    ) -> Completion:
        """Drive one stage as a tool-use loop: the model fetches evidence via
        tools, observes results, and iterates until it stops requesting tools
        (or max_turns is hit), then returns its written section."""
        messages: list[dict] = [{"role": "user", "content": prompt}]
        input_tokens = output_tokens = 0
        text = ""
        turns = 0

        for turn in range(1, max_turns + 1):
            turns = turn
            response = self._client.messages.create(
                model=self._model,
                max_tokens=4096,
                system=system,
                tools=tools,
                messages=messages,
            )
            input_tokens += response.usage.input_tokens
            output_tokens += response.usage.output_tokens
            text = "".join(block.text for block in response.content if block.type == "text")

            if response.stop_reason != "tool_use":
                break

            messages.append({"role": "assistant", "content": response.content})
            tool_results = [
                {
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": execute(block.name, block.input or {}),
                }
                for block in response.content
                if block.type == "tool_use"
            ]
            messages.append({"role": "user", "content": tool_results})

        return Completion(
            text=text, input_tokens=input_tokens, output_tokens=output_tokens, turns=turns
        )
