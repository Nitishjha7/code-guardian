"""Prometheus metrics.

Each one answers a question the project already asks elsewhere - whether
routing saves cost, how often an audit fails - rather than being a generic
request counter.

``prometheus_client`` over a hand-rolled exposition format: the text format has
escaping and type-comment rules that are easy to get subtly wrong.
"""

from __future__ import annotations

from prometheus_client import Counter, Histogram

# --------------------------------------------------------------------------- #
# Reviews
# --------------------------------------------------------------------------- #

REVIEWS_TOTAL = Counter(
    "guardian_reviews_total",
    "Reviews completed, by which auditors the supervisor actually routed to.",
    ["route"],  # "none" | "security" | "performance" | "both"
)

REVIEW_DURATION_SECONDS = Histogram(
    "guardian_review_duration_seconds",
    "Wall-clock time for one review, end to end.",
    # Buckets chosen for the gap that matters here - roughly 1s when nothing
    # routed against 10s+ when both auditors ran - not a generic latency curve.
    buckets=(0.5, 1, 2, 5, 10, 20, 40),
)

FINDINGS_TOTAL = Counter(
    "guardian_findings_total",
    "Findings reported, by auditor and severity.",
    ["auditor", "severity"],  # auditor: "security" | "performance"
)

AUDIT_FAILURES_TOTAL = Counter(
    "guardian_audit_failures_total",
    "Audits invoked but that never produced a result (dead model, rate limit, bad key).",
    ["auditor"],
)

# --------------------------------------------------------------------------- #
# The LLM gateway
# --------------------------------------------------------------------------- #

LLM_CALLS_TOTAL = Counter(
    "guardian_llm_calls_total",
    "LLM calls that actually returned a response, by model.",
    ["model"],
)

LLM_FALLBACK_TRIGGERED_TOTAL = Counter(
    "guardian_llm_fallback_triggered_total",
    "Times the primary model failed and a fallback model answered instead.",
)

TOKENS_TOTAL = Counter(
    "guardian_llm_tokens_total",
    "Tokens consumed, by model and direction.",
    ["model", "direction"],  # direction: "input" | "output"
)


def record_review(state: dict, primary_model: str | None = None) -> None:
    """Update every review-level metric from one finished ``ReviewerState``.

    Called once per review from ``run_review`` and ``run_review_stream``,
    rather than scattering ``.inc()`` calls through the graph nodes: the nodes
    stay untouched and this is the only place that knows the metric names.
    """
    routed = state.get("routed_to") or []
    route = (
        "both" if len(routed) == 2 else routed[0].removesuffix("_audit") if routed else "none"
    )
    REVIEWS_TOTAL.labels(route=route).inc()

    for finding in state.get("security_issues") or []:
        FINDINGS_TOTAL.labels(auditor="security", severity=finding.get("severity", "Medium")).inc()
    for finding in state.get("performance_issues") or []:
        FINDINGS_TOTAL.labels(auditor="performance", severity=finding.get("severity", "Medium")).inc()

    for auditor in state.get("failed_audits") or []:
        AUDIT_FAILURES_TOTAL.labels(auditor=auditor.removesuffix("_audit")).inc()

    usage = (state.get("token_usage") or {}).get("by_model") or {}
    models_that_answered = list(usage.keys())
    for model, stats in usage.items():
        LLM_CALLS_TOTAL.labels(model=model).inc(stats.get("calls", 0))
        TOKENS_TOTAL.labels(model=model, direction="input").inc(stats.get("input_tokens", 0))
        TOKENS_TOTAL.labels(model=model, direction="output").inc(stats.get("output_tokens", 0))

    # A fallback fired if more than one model answered, or if the only model
    # that answered was not the configured primary. The second case is why
    # ``primary_model`` is passed in — one model answering proves nothing on
    # its own.
    fell_back = len(models_that_answered) > 1 or (
        primary_model is not None
        and len(models_that_answered) == 1
        and models_that_answered[0] != primary_model
    )
    if fell_back:
        LLM_FALLBACK_TRIGGERED_TOTAL.inc()
