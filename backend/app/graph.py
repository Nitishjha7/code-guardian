"""The LangGraph state machine.

Topology (docs/TECHNICAL_SPEC.md §3):

    supervisor --[tool_calls present]--> tools --> supervisor   (loop)
    supervisor --[no tool_calls]-------> collect --> patch --> guardrail --> END

The supervisor loop is wired explicitly rather than via ``create_react_agent``:
the orchestration is the reviewable artifact of this project, so hiding the
state transitions behind a prebuilt would defeat the point.
"""

from __future__ import annotations

import json
import time

from langchain_core.messages import ToolMessage
from langgraph.graph import END, StateGraph
from langgraph.prebuilt import ToolNode

from .agents import patch_generator, supervisor
from .guardrails_config import validate_output
from .state import Finding, ReviewerState

_SEVERITY_ORDER = {"Critical": 0, "High": 1, "Medium": 2, "Low": 3}


# --------------------------------------------------------------------------- #
# Nodes
# --------------------------------------------------------------------------- #

def _route_after_supervisor(state: ReviewerState) -> str:
    """Loop back into the tools while the model is still requesting audits."""
    messages = state.get("messages") or []
    if messages and getattr(messages[-1], "tool_calls", None):
        return "tools"
    return "collect"


def collect_node(state: ReviewerState) -> dict:
    """Fold the ToolMessages produced by the audits into typed state.

    The tools return JSON strings because that is what a ToolNode can carry;
    this is where those strings become ``security_issues`` / ``performance_issues``
    so that nothing downstream has to re-parse message history.
    """
    security: list[Finding] = []
    performance: list[Finding] = []
    routed: list[str] = []

    for message in state.get("messages") or []:
        if not isinstance(message, ToolMessage):
            continue
        try:
            findings = json.loads(message.content or "[]")
        except (json.JSONDecodeError, TypeError):
            findings = []
        if not isinstance(findings, list):
            findings = []

        if message.name == "security_audit":
            security.extend(f for f in findings if isinstance(f, dict))
            routed.append("security_audit")
        elif message.name == "performance_audit":
            performance.extend(f for f in findings if isinstance(f, dict))
            routed.append("performance_audit")

    security.sort(key=lambda f: _SEVERITY_ORDER.get(f.get("severity", "Medium"), 2))
    performance.sort(key=lambda f: _SEVERITY_ORDER.get(f.get("severity", "Medium"), 2))

    return {
        "security_issues": security,
        "performance_issues": performance,
        "routed_to": sorted(set(routed)),
        "logs": [
            f"Collector: {len(security)} security finding(s), "
            f"{len(performance)} performance finding(s)."
        ],
    }


def patch_node(state: ReviewerState) -> dict:
    """Synthesize both audits into a corrected file and an exact unified diff."""
    security = state.get("security_issues") or []
    performance = state.get("performance_issues") or []

    if not security and not performance:
        return {
            "fixed_code": state.get("source_code", ""),
            "diff": "",
            "logs": ["Patch generator: no findings to fix, skipped."],
        }

    fixed_code, diff = patch_generator.generate(
        source_code=state.get("source_code", ""),
        language=state.get("language", "python"),
        security_issues=security,
        performance_issues=performance,
    )
    log = (
        f"Patch generator: produced a patch ({len(diff.splitlines())} diff line(s))."
        if diff
        else "Patch generator: model returned no change."
    )
    return {"fixed_code": fixed_code, "diff": diff, "logs": [log]}


def _render_report(state: ReviewerState, diff: str) -> str:
    """Build the GitHub-ready markdown review."""
    security = state.get("security_issues") or []
    performance = state.get("performance_issues") or []
    routed = state.get("routed_to") or []

    lines = ["## Code Guardian Review", ""]

    if not routed:
        lines += [
            "The supervisor determined this submission needed no specialist audit.",
            "",
        ]
    else:
        pretty = ", ".join(r.replace("_", " ") for r in routed)
        lines += [f"_Auditors run: {pretty}._", ""]

    severe = sum(
        1 for f in security + performance if f.get("severity") in ("Critical", "High")
    )
    lines += [
        f"**{len(security)} security** / **{len(performance)} performance** "
        f"finding(s) - {severe} at High or Critical severity.",
        "",
    ]

    def section(title: str, findings: list[Finding], perf: bool = False) -> list[str]:
        if not findings:
            return [f"### {title}", "", "No issues found.", ""]
        out = [f"### {title}", ""]
        for f in findings:
            severity = f.get("severity", "Medium")
            name = f.get("title", "Untitled finding")
            out += [f"<details><summary><b>[{severity}] {name}</b></summary>", ""]
            if f.get("line_hint"):
                out += ["`" + str(f["line_hint"]) + "`", ""]
            if f.get("explanation"):
                out += [f"**Why:** {f['explanation']}", ""]
            if perf and f.get("complexity_before", "n/a") != "n/a":
                out += [
                    f"**Complexity:** {f.get('complexity_before')} -> "
                    f"{f.get('complexity_after')}",
                    "",
                ]
            if f.get("recommendation"):
                out += [f"**Fix:** {f['recommendation']}", ""]
            out += ["</details>", ""]
        return out

    lines += section("Security", security)
    lines += section("Performance", performance, perf=True)

    if diff:
        lines += ["### Suggested patch", "", "```diff", diff.rstrip("\n"), "```", ""]
    else:
        lines += ["### Suggested patch", "", "_No patch generated._", ""]

    lines.append("<sub>Generated by Code Guardian - review before merging.</sub>")
    return "\n".join(lines)


def guardrail_node(state: ReviewerState) -> dict:
    """Last gate: nothing leaves carrying a credential.

    The report is rendered *before* validation so that a secret the model copied
    into prose is caught too, not just one sitting inside the code block.
    """
    diff = state.get("diff", "")
    report_md = _render_report(state, diff)

    (clean_diff, clean_report, clean_fixed), guard_report = validate_output(
        diff, report_md, state.get("fixed_code", "")
    )

    if guard_report["passed"]:
        detail = "passed."
    else:
        detail = (
            f"{len(guard_report['secrets_found'])} secret pattern(s), "
            f"{guard_report['redactions']} redaction(s), "
            f"{len(guard_report['tone_flags'])} tone flag(s)."
        )

    return {
        "diff": clean_diff,
        "fixed_code": clean_fixed,
        "summary_report": clean_report,
        "guardrail_report": guard_report,
        "logs": [f"Guardrails ({guard_report['engine']}): {detail}"],
    }


# --------------------------------------------------------------------------- #
# Graph construction
# --------------------------------------------------------------------------- #

def build_graph():
    """Compile the review graph."""
    builder = StateGraph(ReviewerState)

    builder.add_node("supervisor", supervisor.supervisor_node)
    builder.add_node("tools", ToolNode(supervisor.TOOLS))
    builder.add_node("collect", collect_node)
    builder.add_node("patch", patch_node)
    builder.add_node("guardrail", guardrail_node)

    builder.set_entry_point("supervisor")
    builder.add_conditional_edges(
        "supervisor",
        _route_after_supervisor,
        {"tools": "tools", "collect": "collect"},
    )
    builder.add_edge("tools", "supervisor")
    builder.add_edge("collect", "patch")
    builder.add_edge("patch", "guardrail")
    builder.add_edge("guardrail", END)

    return builder.compile()


_GRAPH = None


def get_graph():
    global _GRAPH
    if _GRAPH is None:
        _GRAPH = build_graph()
    return _GRAPH


def run_review(
    source_code: str,
    language: str = "python",
    force_full_audit: bool = False,
) -> ReviewerState:
    """Execute one full review. The single entry point the API uses."""
    started = time.perf_counter()

    # The tools read the submission from module state rather than taking it as a
    # tool argument - see the note in app/agents/supervisor.py.
    supervisor.set_current_input(source_code, language)

    initial: ReviewerState = {
        "source_code": source_code,
        "language": language,
        "messages": [],
        "security_issues": [],
        "performance_issues": [],
        "force_full_audit": force_full_audit,
        "logs": [f"Review started - language={language} - {len(source_code)} chars."],
    }

    result = get_graph().invoke(initial, config={"recursion_limit": 12})
    elapsed = time.perf_counter() - started
    result["logs"] = list(result.get("logs", [])) + [
        f"Review finished in {elapsed:.2f}s."
    ]
    return result
