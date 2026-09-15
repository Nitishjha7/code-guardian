"""Graph and agent-plumbing tests that need no LLM call.

Everything here targets the deterministic seams: parsing an LLM response,
computing the diff, folding tool results into state, and the routing backstop.
"""

import json

from langchain_core.messages import AIMessage, ToolMessage

from app.agents._common import parse_json_list, strip_code_fence, truncate
from app.agents.patch_generator import make_unified_diff
from app.agents.supervisor import looks_high_stakes
from app.graph import _render_report, _route_after_supervisor, collect_node


# --------------------------------------------------------------------------- #
# Response parsing
# --------------------------------------------------------------------------- #

def test_parse_json_list_handles_bare_array():
    assert parse_json_list('[{"title": "x"}]') == [{"title": "x"}]


def test_parse_json_list_handles_fenced_and_prefixed_output():
    raw = 'Sure! Here are the findings:\n```json\n[{"title": "SQLi"}]\n```'
    assert parse_json_list(raw) == [{"title": "SQLi"}]


def test_parse_json_list_returns_empty_on_garbage():
    assert parse_json_list("no json here at all") == []
    assert parse_json_list("") == []


def test_strip_code_fence_returns_body():
    assert strip_code_fence("```python\nx = 1\n```") == "x = 1"


def test_strip_code_fence_passes_through_unfenced_text():
    assert strip_code_fence("x = 1") == "x = 1"


def test_truncate_marks_the_cut():
    out = truncate("a" * 100, limit=10)
    assert out.startswith("a" * 10)
    assert "truncated" in out


# --------------------------------------------------------------------------- #
# Diff
# --------------------------------------------------------------------------- #

def test_unified_diff_is_empty_when_nothing_changed():
    src = "x = 1\n"
    assert make_unified_diff(src, src) == ""


def test_unified_diff_marks_added_and_removed_lines():
    diff = make_unified_diff("x = 1\n", "x = 2\n", filename="m.py")
    assert "-x = 1" in diff
    assert "+x = 2" in diff
    assert "a/m.py" in diff and "b/m.py" in diff


# --------------------------------------------------------------------------- #
# Routing
# --------------------------------------------------------------------------- #

def test_router_loops_while_tool_calls_are_pending():
    msg = AIMessage(
        content="",
        tool_calls=[{"name": "security_audit", "args": {}, "id": "1"}],
    )
    assert _route_after_supervisor({"messages": [msg]}) == "tools"


def test_router_exits_when_no_tool_calls_remain():
    assert _route_after_supervisor({"messages": [AIMessage(content="done")]}) == "collect"


def test_high_stakes_backstop_catches_auth_and_db_surfaces():
    assert looks_high_stakes("cursor.execute('SELECT * FROM users')")
    assert looks_high_stakes("def check_password(raw, stored):")
    assert looks_high_stakes("subprocess.run(cmd)")


def test_high_stakes_backstop_leaves_plain_styling_alone():
    assert not looks_high_stakes(".card { display: flex; gap: 12px; }")


# --------------------------------------------------------------------------- #
# Collector
# --------------------------------------------------------------------------- #

def _tool_message(name, findings):
    return ToolMessage(
        content=json.dumps({"ok": True, "findings": findings}),
        name=name,
        tool_call_id=name,
    )


def _failed_tool_message(name, error):
    return ToolMessage(
        content=json.dumps({"ok": False, "error": error}),
        name=name,
        tool_call_id=name,
    )


def test_collect_node_sorts_findings_by_severity():
    state = {
        "messages": [
            _tool_message(
                "security_audit",
                [
                    {"title": "low one", "severity": "Low"},
                    {"title": "critical one", "severity": "Critical"},
                    {"title": "medium one", "severity": "Medium"},
                ],
            )
        ]
    }
    out = collect_node(state)
    assert [f["title"] for f in out["security_issues"]] == [
        "critical one",
        "medium one",
        "low one",
    ]
    assert out["routed_to"] == ["security_audit"]
    assert out["performance_issues"] == []


def test_a_failed_audit_is_never_reported_as_clean():
    """The single most dangerous bug this system can have.

    If an audit raises (dead model, bad key, rate limit) and that is folded into
    "no findings", the review tells the user their vulnerable code is clean.
    """
    state = {
        "messages": [
            _failed_tool_message("security_audit", "NotFoundError: model decommissioned")
        ]
    }
    out = collect_node(state)

    assert out["security_issues"] == []
    assert out["failed_audits"] == ["security_audit"]
    assert "model decommissioned" in out["audit_errors"][0]


def test_unparseable_tool_result_counts_as_a_failure_not_an_empty_pass():
    """ToolNode renders an uncaught exception as plain text, not JSON."""
    state = {
        "messages": [
            ToolMessage(
                content="Error: APIConnectionError", name="security_audit", tool_call_id="1"
            )
        ]
    }
    out = collect_node(state)

    assert out["security_issues"] == []
    assert out["failed_audits"] == ["security_audit"]
    # The auditor still ran, so the UI must not claim it was routed around.
    assert out["routed_to"] == ["security_audit"]


def test_one_failed_audit_does_not_discard_the_other():
    state = {
        "messages": [
            _failed_tool_message("security_audit", "boom"),
            _tool_message("performance_audit", [{"title": "p", "severity": "High"}]),
        ]
    }
    out = collect_node(state)

    assert out["failed_audits"] == ["security_audit"]
    assert len(out["performance_issues"]) == 1


def test_report_refuses_to_show_a_failed_audit_as_no_issues_found():
    report = _render_report(
        {
            "security_issues": [],
            "performance_issues": [],
            "routed_to": ["security_audit", "performance_audit"],
            "failed_audits": ["security_audit"],
            "audit_errors": ["security_audit: boom"],
        },
        diff="",
    )

    assert "This review is incomplete" in report
    assert "Audit failed" in report
    # The clean-pass wording must not appear anywhere in the security section.
    security_section = report.split("### Security")[1].split("### Performance")[0]
    assert "No issues found" not in security_section


def test_collect_node_records_both_auditors():
    state = {
        "messages": [
            _tool_message("security_audit", [{"title": "s", "severity": "High"}]),
            _tool_message("performance_audit", [{"title": "p", "severity": "Medium"}]),
        ]
    }
    out = collect_node(state)
    assert out["routed_to"] == ["performance_audit", "security_audit"]
    assert len(out["security_issues"]) == 1
    assert len(out["performance_issues"]) == 1


# --------------------------------------------------------------------------- #
# run_review_stream
# --------------------------------------------------------------------------- #
#
# These test the generator's contract against a fake compiled graph, not the
# real one - the real graph needs a live model and is exercised separately
# (README "Verified" table, and by hand against /api/review/stream). What is
# tested here is the seam that would break silently: does each node update
# turn into exactly one progress event, does state accumulate the way
# LangGraph's own merge does, and does the final event carry the complete
# state - all independent of any LLM call.

class _FakeCompiledGraph:
    """Stands in for ``get_graph()``. ``updates`` mirrors what
    ``graph.stream(..., stream_mode="updates")`` yields: one
    ``{node_name: partial_state}`` dict per node completion."""

    def __init__(self, updates):
        self._updates = updates

    def stream(self, state, config=None, stream_mode=None):
        assert stream_mode == "updates"
        yield from self._updates


def test_stream_emits_one_progress_event_per_node_update(monkeypatch):
    import app.graph as graph_module

    fake = _FakeCompiledGraph([
        {"supervisor": {"messages": []}},
        {"collect": {"routed_to": []}},
    ])
    monkeypatch.setattr(graph_module, "get_graph", lambda: fake)

    events = list(graph_module.run_review_stream("body { color: red; }", "css"))

    kinds = [kind for kind, _ in events]
    assert kinds == ["progress", "progress", "done"]
    assert events[0][1]["node"] == "supervisor"
    assert events[1][1]["node"] == "collect"


def test_stream_a_node_looped_twice_emits_two_events(monkeypatch):
    """The supervisor/tools loop can run more than once - each pass through
    "tools" is its own event, not deduplicated away."""
    import app.graph as graph_module

    fake = _FakeCompiledGraph([
        {"supervisor": {}},
        {"tools": {}},
        {"supervisor": {}},
        {"tools": {}},
        {"collect": {}},
    ])
    monkeypatch.setattr(graph_module, "get_graph", lambda: fake)

    nodes = [
        payload["node"]
        for kind, payload in graph_module.run_review_stream("x", "python")
        if kind == "progress"
    ]
    assert nodes == ["supervisor", "tools", "supervisor", "tools", "collect"]


def test_stream_final_state_accumulates_across_node_updates(monkeypatch):
    """The "done" payload has to reflect every node's contribution, the same
    way LangGraph merges partial updates into one state - not just the last
    node's return value."""
    import app.graph as graph_module

    fake = _FakeCompiledGraph([
        {"supervisor": {"messages": []}},
        {"collect": {"routed_to": ["security_audit"], "risk": {"score": 80, "band": "high"}}},
        {"patch": {"fixed_code": "safe_code_here"}},
        {"guardrail": {"guardrail_report": {"engine": "local-pattern-scanner", "passed": True}}},
    ])
    monkeypatch.setattr(graph_module, "get_graph", lambda: fake)

    *_, (kind, final_state) = graph_module.run_review_stream("x", "python")

    assert kind == "done"
    assert final_state["routed_to"] == ["security_audit"]
    assert final_state["risk"]["band"] == "high"
    assert final_state["fixed_code"] == "safe_code_here"
    assert final_state["guardrail_report"]["passed"] is True
    # And still carries what run_review's own return value always has.
    assert any("Review finished in" in line for line in final_state["logs"])


def test_stream_unknown_node_falls_back_to_its_own_name(monkeypatch):
    """A label is presentation only - a graph change that adds a node before
    _NODE_LABELS is updated should degrade to the raw node name, not crash."""
    import app.graph as graph_module

    fake = _FakeCompiledGraph([{"some_new_node": {}}])
    monkeypatch.setattr(graph_module, "get_graph", lambda: fake)

    kind, payload = next(graph_module.run_review_stream("x", "python"))
    assert payload["label"] == "some_new_node"
