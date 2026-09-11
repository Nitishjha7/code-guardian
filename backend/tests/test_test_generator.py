"""Test Generation Agent tests.

The generation itself needs an LLM, so what is tested here is the selection
rule and the routing predicate - the parts that decide whether a call is made
at all, and which are the parts that can silently do the wrong thing.
"""

from app.agents.test_generator import generate, worth_testing
from app.graph import _route_after_patch


def _sec(severity, title="finding"):
    return {"severity": severity, "title": title, "source": "llm"}


def _perf(severity, title="slow"):
    return {"severity": severity, "title": title, "source": "llm"}


# --------------------------------------------------------------------------- #
# Selection
# --------------------------------------------------------------------------- #

def test_only_critical_and_high_security_findings_are_tested():
    selected = worth_testing(
        [_sec("Critical", "a"), _sec("High", "b"), _sec("Medium", "c"), _sec("Low", "d")],
        [],
    )
    assert [f["title"] for f in selected] == ["a", "b"]


def test_performance_findings_never_get_a_generated_test():
    """A benchmark threshold picked by an LLM with no machine to measure on is
    a flaky test, which is worse than no test."""
    assert worth_testing([], [_perf("Critical"), _perf("High")]) == []


def test_nothing_is_selected_when_there_are_no_findings():
    assert worth_testing([], []) == []


# --------------------------------------------------------------------------- #
# Routing
# --------------------------------------------------------------------------- #

def test_the_graph_skips_test_generation_when_nothing_is_worth_testing():
    state = {"security_issues": [_sec("Low")], "performance_issues": [_perf("High")]}
    assert _route_after_patch(state) == "guardrail"


def test_the_graph_generates_tests_for_a_high_security_finding():
    state = {"security_issues": [_sec("High")], "performance_issues": []}
    assert _route_after_patch(state) == "tests"


def test_routing_survives_an_empty_state():
    assert _route_after_patch({}) == "guardrail"


# --------------------------------------------------------------------------- #
# Generation guards (no LLM call reached)
# --------------------------------------------------------------------------- #

def test_no_findings_means_no_llm_call():
    tests, note = generate("x = 1", "python", [])
    assert tests == ""
    assert "no Critical or High" in note


def test_an_unsupported_language_is_reported_not_guessed():
    tests, note = generate("body { color: red }", "css", [_sec("Critical")])
    assert tests == ""
    assert "css" in note
