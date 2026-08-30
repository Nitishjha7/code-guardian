"""Helpers shared by the specialist agents."""

from __future__ import annotations

import json
import re
from typing import Any

_JSON_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)
_CODE_FENCE = re.compile(r"```[a-zA-Z0-9_+-]*\s*\n(.*?)```", re.DOTALL)


def parse_json_list(raw: str) -> list[dict[str, Any]]:
    """Pull a JSON array out of an LLM response.

    Groq's Llama models mostly honour "reply with JSON only", but they still
    occasionally wrap it in a fence or prepend a sentence. Rather than fail the
    whole review on a formatting slip we recover the array, and return an empty
    list if there genuinely isn't one.
    """
    if not raw:
        return []

    candidates = [m.group(1) for m in _JSON_FENCE.finditer(raw)]
    candidates.append(raw)

    for candidate in candidates:
        candidate = candidate.strip()
        start, end = candidate.find("["), candidate.rfind("]")
        if start == -1 or end <= start:
            continue
        try:
            parsed = json.loads(candidate[start : end + 1])
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, list):
            return [item for item in parsed if isinstance(item, dict)]
    return []


def strip_code_fence(raw: str) -> str:
    """Return the contents of the first fenced block, or the text unchanged."""
    if not raw:
        return ""
    match = _CODE_FENCE.search(raw)
    return (match.group(1) if match else raw).strip()


def truncate(code: str, limit: int = 24_000) -> str:
    """Cap what we send to the model so one huge diff cannot blow the context."""
    if len(code) <= limit:
        return code
    return code[:limit] + "\n\n... [truncated: input exceeded {} characters]".format(limit)
