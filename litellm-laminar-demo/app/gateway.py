"""LiteLLM Router gateway plus the attributes written on every LLM span.

Model calls go through a ``litellm.Router`` rather than bare ``acompletion``.
Each model group is named after the selection it serves,
``<model>__reasoning-<effort>``, and every deployment carries ``model_info``
with the provider name and the base model key, so usage and cost tracking
key on the model rather than the provider-specific deployment string.

The Laminar LLM span around each call gets, by hand:
  - usage: tokens, reasoning, cache read/creation, cache hit %, visible output
  - resolved config: reasoning effort, fast-mode flag
  - content: ``gen_ai.input.messages``, ``gen_ai.output.messages`` and
    ``gen_ai.tool.definitions``, which Laminar lifts into its input, output
    and tool-definition columns
  - the route event (``route_audit``)
"""

import json
import os
from dataclasses import dataclass
from typing import Any

import litellm
from lmnr import Laminar

MODEL = os.environ.get("MODEL", "gpt-4o-mini")
REASONING_EFFORT = os.environ.get("REASONING_EFFORT", "medium")
MOCK_LLM = os.environ.get("MOCK_LLM", "false").lower() == "true"

# Tool arguments that may carry secrets are blanked in traced messages.
_REDACTED_TOOL_ARGUMENTS = frozenset({"set_secret", "write_env_file"})


@dataclass(frozen=True)
class Selection:
    """The model a call resolved to and the Router group that serves it."""

    model: str
    provider: str
    reasoning_effort: str

    @property
    def model_key(self) -> str:
        return self.model.split("/", 1)[-1]

    @property
    def alias(self) -> str:
        return f"{self.model_key}__reasoning-{self.reasoning_effort}"


def _provider_of(model: str) -> str:
    return model.split("/", 1)[0] if "/" in model else "openai"


def default_selection() -> Selection:
    return Selection(MODEL, _provider_of(MODEL), REASONING_EFFORT)


def build_router(selections: list[Selection]) -> litellm.Router:
    model_list = []
    for selection in selections:
        params: dict[str, Any] = {"model": selection.model, "order": 1}
        if MOCK_LLM:
            params["api_key"] = "sk-mock"
        model_list.append(
            {
                "model_name": selection.alias,
                "litellm_params": params,
                "model_info": {"_provider_name": selection.provider, "_model_key": selection.model_key},
            }
        )
    return litellm.Router(
        model_list=model_list,
        routing_strategy="usage-based-routing",
        cooldown_time=10,
        num_retries=3,
        retry_after=5,
        timeout=600.0,
        # One deployment per group: cooling it down would leave nothing to route to.
        disable_cooldowns=len(model_list) <= 1,
    )


def _sanitize(value: Any) -> Any:
    """Drop image payloads and secret-bearing tool arguments from traced content."""
    if isinstance(value, list):
        return [_sanitize(item) for item in value]
    if not isinstance(value, dict):
        if isinstance(value, str) and value.startswith("data:image/"):
            return "[REDACTED_IMAGE]"
        return value
    clean = {k: ("[REDACTED_IMAGE]" if k in {"image", "image_url"} else _sanitize(v)) for k, v in value.items()}
    function = clean.get("function")
    if isinstance(function, dict) and function.get("name") in _REDACTED_TOOL_ARGUMENTS:
        function["arguments"] = "{}"
    return clean


def serialize_messages(messages: list[dict]) -> str:
    return json.dumps([_sanitize(dict(m)) for m in messages], default=str)


def serialize_output(message: dict) -> str:
    entry: dict[str, Any] = {"role": message.get("role", "assistant")}
    if message.get("content") is not None:
        entry["content"] = message["content"]
    if message.get("tool_calls"):
        entry["tool_calls"] = [
            {
                "id": call.get("id", ""),
                "type": call.get("type", "function"),
                "function": {
                    "name": call["function"]["name"],
                    "arguments": "{}"
                    if call["function"]["name"] in _REDACTED_TOOL_ARGUMENTS
                    else call["function"].get("arguments", ""),
                },
            }
            for call in message["tool_calls"]
        ]
    return json.dumps([entry], default=str)


def usage_attributes(selection: Selection, usage: Any) -> dict[str, Any]:
    prompt = getattr(usage, "prompt_tokens", 0) or 0
    completion = getattr(usage, "completion_tokens", 0) or 0
    prompt_details = getattr(usage, "prompt_tokens_details", None)
    completion_details = getattr(usage, "completion_tokens_details", None)
    cached = getattr(prompt_details, "cached_tokens", 0) or 0
    cache_creation = getattr(usage, "cache_creation_input_tokens", 0) or 0
    reasoning = getattr(completion_details, "reasoning_tokens", 0) or 0
    attrs: dict[str, Any] = {
        "gen_ai.system": selection.provider,
        "gen_ai.request.model": selection.model_key,
        "gen_ai.response.model": selection.model_key,
        "gen_ai.usage.input_tokens": prompt,
        "gen_ai.usage.output_tokens": completion,
        "llm.usage.total_tokens": getattr(usage, "total_tokens", None) or prompt + completion,
        "llm.usage.visible_output_tokens": max(completion - reasoning, 0),
        "cache.read_tokens": cached,
        "cache.creation_tokens": cache_creation,
        "cache.hit_pct": round(cached * 100.0 / prompt, 1) if prompt else 0.0,
        "llm.resolved.reasoning_effort": selection.reasoning_effort,
        "llm.model_selection.fast_mode_enabled": False,
    }
    # Written only when non-zero, so absence means "none" rather than "unknown".
    if reasoning:
        attrs["gen_ai.usage.reasoning.output_tokens"] = reasoning
    if cached:
        attrs["gen_ai.usage.cache_read_input_tokens"] = cached
    if cache_creation:
        attrs["gen_ai.usage.cache_creation_input_tokens"] = cache_creation
    return attrs


def record_llm_span(
    selection: Selection,
    usage: Any,
    messages: list[dict],
    output: dict,
    tools: list[dict] | None,
) -> None:
    attrs = usage_attributes(selection, usage)
    attrs["gen_ai.input.messages"] = serialize_messages(messages)
    attrs["gen_ai.output.messages"] = serialize_output(output)
    if tools:
        attrs["gen_ai.tool.definitions"] = json.dumps(tools)
    Laminar.set_span_attributes(attrs)
