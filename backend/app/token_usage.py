"""Per-review token and cost accounting.

Every agent gets its LLM client from ``config.get_llm()``, which is
``@lru_cache``'d — five agents share two or three actual ``ChatGroq``
instances, not one client each. That caching is why this is not "add a
counter to each agent": a counter living on the shared client would mix
tokens from concurrent reviews together, and the whole point of tracking
usage is to answer "what did *this* review cost", not "what has this process
cost since it booted".

The fix is a `contextvars.ContextVar` rather than a global: `run_review` (or
the streaming variant) opens one `UsageTracker` per call, and every LLM
invocation during that call — no matter which of the five agents, no matter
which node in the graph — records into that one instance because the callback
bound onto the shared client (once, in `config.get_llm`) always reads
"whichever tracker is current" rather than holding a reference to one. Two
reviews running concurrently under `anyio.CapacityLimiter(4)` each see only
their own tokens.
"""

from __future__ import annotations

import contextvars
from dataclasses import dataclass, field

from langchain_core.callbacks.base import BaseCallbackHandler

# Per-million-token prices, USD, current as of the models this project uses.
# Deliberately small and inline rather than a pulled-in pricing library: it is
# two numbers that Groq publishes, and a dependency for two numbers is not a
# good trade. Update alongside GUARDIAN_MODEL / GUARDIAN_FALLBACK_MODELS if the
# configured models change — an unlisted model prices at $0, which shows up
# plainly in the UI as "$0.00" rather than silently guessing a number.
_PRICE_PER_MILLION_USD = {
    "openai/gpt-oss-120b": {"input": 0.15, "output": 0.75},
    "openai/gpt-oss-20b": {"input": 0.10, "output": 0.50},
}


@dataclass
class ModelUsage:
    calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


@dataclass
class UsageTracker:
    """Accumulates token usage across every LLM call in one review."""

    by_model: dict[str, ModelUsage] = field(default_factory=dict)

    def record(self, model: str, input_tokens: int, output_tokens: int) -> None:
        usage = self.by_model.setdefault(model, ModelUsage())
        usage.calls += 1
        usage.input_tokens += input_tokens
        usage.output_tokens += output_tokens

    def summary(self) -> dict:
        """The shape returned to the API — see ``ReviewerState["token_usage"]``."""
        by_model = {}
        total_tokens = 0
        total_cost = 0.0
        priced_every_model = True

        for model, usage in self.by_model.items():
            price = _PRICE_PER_MILLION_USD.get(model)
            cost = None
            if price is not None:
                cost = (
                    usage.input_tokens * price["input"]
                    + usage.output_tokens * price["output"]
                ) / 1_000_000
                total_cost += cost
            else:
                priced_every_model = False
            by_model[model] = {
                "calls": usage.calls,
                "input_tokens": usage.input_tokens,
                "output_tokens": usage.output_tokens,
                "total_tokens": usage.total_tokens,
                # None, not 0.0 — an unpriced model costing "nothing" is a
                # different claim than "we don't know the price", and only one
                # of those is true.
                "cost_usd": cost,
            }
            total_tokens += usage.total_tokens

        return {
            "by_model": by_model,
            "total_tokens": total_tokens,
            # If any model that ran isn't in the price table, the total is a
            # lower bound, not a real total — say so rather than quietly
            # under-reporting a number a reader might repeat elsewhere.
            "total_cost_usd": total_cost if priced_every_model else None,
        }


_current: contextvars.ContextVar[UsageTracker | None] = contextvars.ContextVar(
    "guardian_usage_tracker", default=None
)


class _TrackingCallback(BaseCallbackHandler):
    """Bound once onto every LLM client `get_llm()` builds. Stateless by
    itself — reads whatever tracker is current for this call, via the
    contextvar above, so the same callback instance is safe to share across
    every cached client and every concurrent review."""

    def on_llm_end(self, response, **kwargs) -> None:  # noqa: D102 - see class docstring
        tracker = _current.get()
        if tracker is None:
            return
        llm_output = response.llm_output or {}
        model = llm_output.get("model_name", "unknown")
        usage = llm_output.get("token_usage") or {}
        tracker.record(
            model=model,
            input_tokens=usage.get("prompt_tokens", 0),
            output_tokens=usage.get("completion_tokens", 0),
        )


# The one callback instance every `get_llm()` client is bound to.
TRACKING_CALLBACK = _TrackingCallback()


def new_tracker() -> UsageTracker:
    """Start tracking for one review. Call this, run the graph, then call
    ``pop_tracker()`` — see ``graph.run_review`` for the pattern."""
    tracker = UsageTracker()
    _current.set(tracker)
    return tracker
