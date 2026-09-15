"""``UsageTracker`` and the contextvar plumbing around it.

The one thing worth testing here is scope: a callback shared across every
cached ``ChatGroq`` client (see config.py's ``_client``) has to attribute
tokens to the *current* review, not leak between two trackers or between
concurrent requests. Real Groq usage is exercised live — see the README's
"Verified" table — not re-simulated here.
"""

from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult

from app.token_usage import TRACKING_CALLBACK, UsageTracker, new_tracker


def _llm_result(model: str, prompt_tokens: int, completion_tokens: int) -> ChatResult:
    message = AIMessage(content="answer")
    return ChatResult(
        generations=[ChatGeneration(message=message)],
        llm_output={
            "model_name": model,
            "token_usage": {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": prompt_tokens + completion_tokens,
            },
        },
    )


def test_record_accumulates_across_multiple_calls_to_the_same_model():
    tracker = UsageTracker()
    tracker.record("openai/gpt-oss-120b", input_tokens=100, output_tokens=50)
    tracker.record("openai/gpt-oss-120b", input_tokens=80, output_tokens=40)

    summary = tracker.summary()
    usage = summary["by_model"]["openai/gpt-oss-120b"]
    assert usage["calls"] == 2
    assert usage["input_tokens"] == 180
    assert usage["output_tokens"] == 90
    assert usage["total_tokens"] == 270


def test_summary_prices_a_known_model():
    tracker = UsageTracker()
    tracker.record("openai/gpt-oss-120b", input_tokens=1_000_000, output_tokens=1_000_000)

    summary = tracker.summary()
    usage = summary["by_model"]["openai/gpt-oss-120b"]
    # $0.15 in + $0.75 out per the price table in token_usage.py
    assert usage["cost_usd"] == 0.90
    assert summary["total_cost_usd"] == 0.90


def test_an_unpriced_model_reports_none_not_zero():
    """A model missing from the price table should surface as "unknown", not
    as a silent $0 that reads as free."""
    tracker = UsageTracker()
    tracker.record("some-new-model", input_tokens=1_000, output_tokens=1_000)

    summary = tracker.summary()
    assert summary["by_model"]["some-new-model"]["cost_usd"] is None
    assert summary["total_cost_usd"] is None, (
        "one unpriced model makes the review's total cost unknown, "
        "not a partial total that looks complete"
    )


def test_mixed_known_and_unknown_models_still_reports_total_as_none():
    tracker = UsageTracker()
    tracker.record("openai/gpt-oss-120b", input_tokens=1_000_000, output_tokens=0)
    tracker.record("some-new-model", input_tokens=1_000, output_tokens=0)

    summary = tracker.summary()
    # The priced model still gets its own real number...
    assert summary["by_model"]["openai/gpt-oss-120b"]["cost_usd"] == 0.15
    # ...but the review-wide total is honest about not knowing the rest.
    assert summary["total_cost_usd"] is None


def test_the_callback_only_writes_to_the_tracker_current_when_it_fires():
    """The invariant the whole design depends on: the shared callback
    instance has no state of its own, it always reads whichever tracker
    new_tracker() most recently made current."""
    tracker_a = new_tracker()
    TRACKING_CALLBACK.on_llm_end(_llm_result("openai/gpt-oss-120b", 10, 5))
    assert tracker_a.summary()["total_tokens"] == 15

    tracker_b = new_tracker()
    TRACKING_CALLBACK.on_llm_end(_llm_result("openai/gpt-oss-120b", 20, 10))

    # tracker_a must not have grown after control moved to tracker_b.
    assert tracker_a.summary()["total_tokens"] == 15
    assert tracker_b.summary()["total_tokens"] == 30


def test_on_llm_end_with_no_current_tracker_does_not_raise():
    """A stray callback firing outside of run_review/run_review_stream (a
    script, a REPL, a future call site that forgets to call new_tracker())
    must not crash the call — it just isn't counted."""
    import app.token_usage as token_usage_module

    token_usage_module._current.set(None)
    TRACKING_CALLBACK.on_llm_end(_llm_result("openai/gpt-oss-120b", 10, 5))  # must not raise
