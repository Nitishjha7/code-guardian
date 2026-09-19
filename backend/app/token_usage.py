"""Per-review token and cost accounting.

``config.get_llm()`` is ``@lru_cache``'d, so the five agents share two or three
``ChatGroq`` instances. A counter on the shared client would therefore mix
concurrent reviews together, answering "what has this process cost since boot"
instead of "what did *this* review cost".

So the tracker lives in a ``ContextVar``: ``run_review`` opens one per call, and
the callback bound once onto the shared client reads whichever tracker is
current rather than holding a reference to one.
"""

from __future__ import annotations

import contextvars
from dataclasses import dataclass, field

from langchain_core.callbacks.base import BaseCallbackHandler

# Per-million-token prices in USD, inline rather than via a pricing library —
# two published numbers do not justify a dependency. Update alongside
# GUARDIAN_MODEL. An unlisted model prices at $0 and shows "$0.00" in the UI
# rather than a guess.
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
