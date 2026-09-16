"""``record_review`` — the one function that turns a finished review into
metric updates. Each assertion reads the counter's own ``_value.get()`` /
``.collect()`` rather than scraping the text exposition format, since the
format itself is `prometheus_client`'s job to get right, not this project's.
"""

from app.metrics import (
    AUDIT_FAILURES_TOTAL,
    FINDINGS_TOTAL,
    LLM_FALLBACK_TRIGGERED_TOTAL,
    REVIEWS_TOTAL,
    TOKENS_TOTAL,
    record_review,
)


def _counter_value(counter, **labels) -> float:
    return counter.labels(**labels)._value.get()


def test_route_label_is_none_when_nothing_was_routed():
    before = _counter_value(REVIEWS_TOTAL, route="none")
    record_review({"routed_to": []})
    assert _counter_value(REVIEWS_TOTAL, route="none") == before + 1


def test_route_label_is_both_when_two_auditors_ran():
    before = _counter_value(REVIEWS_TOTAL, route="both")
    record_review({"routed_to": ["security_audit", "performance_audit"]})
    assert _counter_value(REVIEWS_TOTAL, route="both") == before + 1


def test_route_label_names_the_single_auditor_that_ran():
    before = _counter_value(REVIEWS_TOTAL, route="security")
    record_review({"routed_to": ["security_audit"]})
    assert _counter_value(REVIEWS_TOTAL, route="security") == before + 1


def test_findings_are_counted_by_auditor_and_severity():
    before = _counter_value(FINDINGS_TOTAL, auditor="security", severity="Critical")
    record_review(
        {
            "routed_to": ["security_audit"],
            "security_issues": [
                {"severity": "Critical"},
                {"severity": "Critical"},
            ],
        }
    )
    assert _counter_value(FINDINGS_TOTAL, auditor="security", severity="Critical") == before + 2


def test_a_failed_audit_is_counted_separately_from_findings():
    before_fail = _counter_value(AUDIT_FAILURES_TOTAL, auditor="security")
    record_review(
        {
            "routed_to": ["security_audit"],
            "security_issues": [],
            "failed_audits": ["security_audit"],
        }
    )
    assert _counter_value(AUDIT_FAILURES_TOTAL, auditor="security") == before_fail + 1


def test_no_fallback_metric_when_only_the_primary_model_answered():
    before = LLM_FALLBACK_TRIGGERED_TOTAL._value.get()
    record_review(
        {
            "routed_to": [],
            "token_usage": {"by_model": {"openai/gpt-oss-120b": {"calls": 1, "input_tokens": 10, "output_tokens": 5}}},
        },
        primary_model="openai/gpt-oss-120b",
    )
    assert LLM_FALLBACK_TRIGGERED_TOTAL._value.get() == before


def test_fallback_metric_fires_when_two_models_answered_in_one_review():
    before = LLM_FALLBACK_TRIGGERED_TOTAL._value.get()
    record_review(
        {
            "routed_to": [],
            "token_usage": {
                "by_model": {
                    "openai/gpt-oss-120b": {"calls": 1, "input_tokens": 10, "output_tokens": 5},
                    "openai/gpt-oss-20b": {"calls": 1, "input_tokens": 10, "output_tokens": 5},
                }
            },
        },
        primary_model="openai/gpt-oss-120b",
    )
    assert LLM_FALLBACK_TRIGGERED_TOTAL._value.get() == before + 1


def test_fallback_metric_fires_when_the_primary_failed_every_call():
    """Only one model answered - but it wasn't the configured primary, which
    only a real fallback (not a routing quirk) explains."""
    before = LLM_FALLBACK_TRIGGERED_TOTAL._value.get()
    record_review(
        {
            "routed_to": [],
            "token_usage": {
                "by_model": {"openai/gpt-oss-20b": {"calls": 3, "input_tokens": 10, "output_tokens": 5}}
            },
        },
        primary_model="openai/gpt-oss-120b",
    )
    assert LLM_FALLBACK_TRIGGERED_TOTAL._value.get() == before + 1


def test_tokens_are_attributed_to_the_model_that_actually_answered():
    before_in = _counter_value(TOKENS_TOTAL, model="openai/gpt-oss-20b", direction="input")
    record_review(
        {
            "routed_to": [],
            "token_usage": {
                "by_model": {"openai/gpt-oss-20b": {"calls": 1, "input_tokens": 42, "output_tokens": 7}}
            },
        }
    )
    assert _counter_value(TOKENS_TOTAL, model="openai/gpt-oss-20b", direction="input") == before_in + 42
