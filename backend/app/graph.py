"""The LangGraph state machine.

Topology (docs/TECHNICAL_SPEC.md §3):

    supervisor --[tool_calls present]--> tools --> supervisor   (loop)
    supervisor --[no tool_calls]-------> collect --> patch --> guardrail --> END
                                                        --> tests --/

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

from . import risk
from .agents import patch_generator, supervisor, test_generator
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


def _unpack_audit(content: object) -> tuple[list[Finding], str | None]:
    """Read one audit's tool result.

    Returns ``(findings, error)``; exactly one of the two is meaningful. Note
    that anything unparseable counts as an *error*, not as an empty result:
    LangGraph's ToolNode turns an uncaught exception into a plain-text
    ToolMessage, and reading that as "no findings" is precisely the silent-pass
    bug this function exists to prevent.
    """
    try:
        payload = json.loads(content or "")
    except (json.JSONDecodeError, TypeError):
        return [], f"unparseable audit result: {str(content)[:200]}"

    if isinstance(payload, dict):
        if not payload.get("ok", False):
            return [], str(payload.get("error", "audit reported failure"))
        raw = payload.get("findings", [])
    elif isinstance(payload, list):
        raw = payload  # tolerated for forward/backward compatibility
    else:
        return [], f"unexpected audit result type: {type(payload).__name__}"

    if not isinstance(raw, list):
        return [], "audit returned a non-list findings field"
    return [f for f in raw if isinstance(f, dict)], None


def collect_node(state: ReviewerState) -> dict:
    """Fold the ToolMessages produced by the audits into typed state.

    The tools return JSON strings because that is what a ToolNode can carry;
    this is where those strings become ``security_issues`` / ``performance_issues``
    so that nothing downstream has to re-parse message history.
    """
    security: list[Finding] = []
    performance: list[Finding] = []
    routed: list[str] = []
    failed: list[str] = []
    errors: list[str] = []

    for message in state.get("messages") or []:
        if not isinstance(message, ToolMessage):
            continue
        if message.name not in ("security_audit", "performance_audit"):
            continue

        routed.append(message.name)
        findings, error = _unpack_audit(message.content)

        if error is not None:
            # An audit that never produced a result must not be rendered as a
            # clean pass. Record it so the report and the API can say so.
            failed.append(message.name)
            errors.append(f"{message.name}: {error}")
            continue

        if message.name == "security_audit":
            security.extend(findings)
        else:
            performance.extend(findings)

    security.sort(key=lambda f: _SEVERITY_ORDER.get(f.get("severity", "Medium"), 2))
    performance.sort(key=lambda f: _SEVERITY_ORDER.get(f.get("severity", "Medium"), 2))

    # Scored here, where the findings are first complete, so every consumer
    # downstream (report, API, PR comment, and the future Check Run gate) reads
    # the same number rather than each deriving its own.
    risk_score = risk.score(
        security_issues=security,
        performance_issues=performance,
        source_code=state.get("source_code", ""),
        failed_audits=sorted(set(failed)),
    )

    log = (
        f"Collector: {len(security)} security finding(s), "
        f"{len(performance)} performance finding(s). {risk.describe(risk_score)}"
    )
    if failed:
        log += f" {len(failed)} audit(s) FAILED: {', '.join(failed)}."

    return {
        "security_issues": security,
        "performance_issues": performance,
        "routed_to": sorted(set(routed)),
        "failed_audits": sorted(set(failed)),
        "audit_errors": errors,
        "risk": risk_score,
        "logs": [log],
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


def _route_after_patch(state: ReviewerState) -> str:
    """Write regression tests only when there is something worth pinning down.

    A deterministic predicate over state the graph already holds, so it lives in
    an edge rather than in a model's judgement - see the design note in
    :mod:`app.agents.test_generator`.
    """
    worth = test_generator.worth_testing(
        state.get("security_issues") or [], state.get("performance_issues") or []
    )
    return "tests" if worth else "guardrail"


def tests_node(state: ReviewerState) -> dict:
    """Generate a regression test per Critical/High security finding."""
    findings = test_generator.worth_testing(
        state.get("security_issues") or [], state.get("performance_issues") or []
    )
    try:
        tests, note = test_generator.generate(
            source_code=state.get("source_code", ""),
            language=state.get("language", "python"),
            findings=findings,
        )
    except Exception as exc:  # noqa: BLE001
        # Tests are a bonus on top of the review; losing them must not lose the
        # review. The failure is recorded, not swallowed.
        return {
            "generated_tests": "",
            "tests_note": f"test generation failed: {exc}",
            "logs": [f"Test generator: FAILED ({type(exc).__name__})."],
        }

    log = (
        f"Test generator: wrote {len(tests.splitlines())} line(s) for "
        f"{len(findings)} finding(s)."
        if tests
        else f"Test generator: nothing generated ({note})."
    )
    return {"generated_tests": tests, "tests_note": note or "", "logs": [log]}


def _render_report(state: ReviewerState, diff: str) -> str:
    """Build the GitHub-ready markdown review."""
    security = state.get("security_issues") or []
    performance = state.get("performance_issues") or []
    routed = state.get("routed_to") or []
    failed = state.get("failed_audits") or []
    errors = state.get("audit_errors") or []

    lines = ["## Code Guardian Review", ""]

    if failed:
        # This banner leads the report on purpose: a reader who skims must not
        # walk away thinking the code was reviewed and came back clean.
        lines += [
            "> **This review is incomplete.** "
            f"{len(failed)} audit(s) failed to run: "
            f"{', '.join(a.replace('_', ' ') for a in failed)}. "
            "Do not treat the sections below as a clean bill of health.",
            "",
        ]
        for err in errors:
            lines.append(f"> - `{err}`")
        lines.append("")

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

    risk_score = state.get("risk") or {}
    if risk_score:
        if risk_score.get("complete", True):
            badge = f"**Risk {risk_score.get('score', 0)}/100 — {str(risk_score.get('band', 'none')).upper()}**"
            lines += [f"{badge}. {risk_score.get('note', '')}", ""]
        else:
            lines += [
                f"**Risk score unavailable.** {risk_score.get('note', '')}",
                "",
            ]

    lines += [
        f"**{len(security)} security** / **{len(performance)} performance** "
        f"finding(s) - {severe} at High or Critical severity.",
        "",
    ]

    def section(
        title: str, findings: list[Finding], tool_name: str, perf: bool = False
    ) -> list[str]:
        if tool_name in failed:
            return [f"### {title}", "", "**Audit failed - this code was not checked.**", ""]
        if tool_name not in routed:
            return [f"### {title}", "", "_Not run: the supervisor routed around it._", ""]
        if not findings:
            return [f"### {title}", "", "No issues found.", ""]
        out = [f"### {title}", ""]
        for f in findings:
            severity = f.get("severity", "Medium")
            name = f.get("title", "Untitled finding")
            # A finding both engines found independently is the one to read
            # first, so the corroboration goes in the collapsed summary line.
            source = str(f.get("source", "llm"))
            tag = " *(confirmed by static analysis)*" if source.startswith("llm+") else (
                f" *({source})*" if source != "llm" else ""
            )
            out += [f"<details><summary><b>[{severity}] {name}</b>{tag}</summary>", ""]
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

    lines += section("Security", security, "security_audit")
    lines += section("Performance", performance, "performance_audit", perf=True)

    if diff:
        lines += ["### Suggested patch", "", "```diff", diff.rstrip("\n"), "```", ""]
    else:
        lines += ["### Suggested patch", "", "_No patch generated._", ""]

    tests = state.get("generated_tests") or ""
    if tests:
        lang = state.get("language", "")
        lines += [
            "### Regression tests",
            "",
            "_Generated, **not executed** - read them before you trust them._",
            "",
            f"```{lang}",
            tests.rstrip("\n"),
            "```",
            "",
        ]

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
    builder.add_node("tests", tests_node)
    builder.add_node("guardrail", guardrail_node)

    builder.set_entry_point("supervisor")
    builder.add_conditional_edges(
        "supervisor",
        _route_after_supervisor,
        {"tools": "tools", "collect": "collect"},
    )
    builder.add_edge("tools", "supervisor")
    builder.add_edge("collect", "patch")
    builder.add_conditional_edges(
        "patch",
        _route_after_patch,
        {"tests": "tests", "guardrail": "guardrail"},
    )
    builder.add_edge("tests", "guardrail")
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
