"""Supervisor — an LLM tool-calling router, not a fixed fan-out.

See docs/TECHNICAL_SPEC.md §3a for the design argument. In short: the
specialists are exposed to the model as tools, and the model decides at runtime
which audits a given input actually needs. The tool docstrings *are* the
routing criteria, so adding a Phase 3 agent means writing one more ``@tool`` —
no edge rewiring.

The known failure mode is a false negative: skipping the security audit on code
that did have a vulnerability. Three mitigations live here:

1. ``temperature=0`` (see :mod:`app.config`) and docstrings written as routing
   criteria rather than prose descriptions.
2. ``force_full_audit`` — a caller-supplied override that bypasses routing
   entirely for high-stakes paths (anything touching auth or database code).
3. ``_looks_high_stakes`` — a cheap static backstop that flips the override on
   when the input obviously touches an auth or DB surface, so the recall risk
   does not depend solely on the caller remembering to set the flag.
"""

from __future__ import annotations

import json
import re

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.tools import tool

from ..config import get_llm
from . import performance_agent, security_agent

# Set by the graph before each run so the tools can see the code without the
# supervisor having to echo an entire diff back through its own tool arguments
# (which would cost the input tokens twice and risk the model truncating it).
_CURRENT: dict[str, str] = {"source_code": "", "language": "python"}


def set_current_input(source_code: str, language: str) -> None:
    _CURRENT["source_code"] = source_code
    _CURRENT["language"] = language


@tool
def security_audit() -> str:
    """Audit the submitted code for security defects.

    Call this when the code does any of: handle user input, build SQL or shell
    commands, authenticate or authorize a request, read or write files or
    network resources, deserialize data, use cryptography, or contain anything
    that looks like a credential.

    Do NOT call this for pure styling (CSS), pure formatting changes, static
    copy or markup with no data handling, or comment-only edits.

    Returns a JSON array of findings with severity ratings.
    """
    findings = security_agent.audit(_CURRENT["source_code"], _CURRENT["language"])
    return json.dumps(findings)


@tool
def performance_audit() -> str:
    """Audit the submitted code for runtime and resource cost.

    Call this when the code contains loops, recursion, collection processing,
    database or network calls, file or stream handling, or any computation whose
    cost grows with input size.

    Do NOT call this for pure configuration files, static markup, styling, or
    declarative data with no execution.

    Returns a JSON array of findings with Big-O before/after where applicable.
    """
    findings = performance_agent.audit(_CURRENT["source_code"], _CURRENT["language"])
    return json.dumps(findings)


TOOLS = [security_audit, performance_audit]
TOOLS_BY_NAME = {t.name: t for t in TOOLS}

SYSTEM_PROMPT = """You are the supervisor of a code review system. You do not \
review code yourself — you decide which specialist auditors a submission needs, \
then stop.

You have two auditors available as tools. Read their descriptions as routing
criteria and call every tool whose criteria the submission meets — one, both, or
neither. Call them in a single turn so they run in parallel.

Bias: when you are genuinely unsure whether the security criteria are met, call
the security auditor. A missed vulnerability costs far more than a wasted audit.

Once the tool results are back, do not call anything else and do not summarise
the findings. Reply with a single short sentence naming which auditors you ran
and why. Another node handles the report."""

_HIGH_STAKES = re.compile(
    r"\b(password|passwd|secret|token|api[_-]?key|credential|auth|login|signin|"
    r"session|jwt|oauth|permission|role|admin|sql|select\s+.*\bfrom\b|insert\s+into|"
    r"update\s+.*\bset\b|delete\s+from|execute|cursor|query|db\.|database|"
    r"subprocess|os\.system|eval|exec|pickle)\b",
    re.IGNORECASE,
)


def looks_high_stakes(source_code: str) -> bool:
    """Cheap static backstop for the router's recall risk.

    Deliberately over-inclusive: a false positive here costs one extra audit,
    a false negative costs a missed vulnerability.
    """
    return bool(_HIGH_STAKES.search(source_code or ""))


def _forced_fan_out() -> AIMessage:
    """Hand-built tool calls that bypass the router entirely."""
    return AIMessage(
        content="",
        tool_calls=[
            {"name": "security_audit", "args": {}, "id": "forced_security"},
            {"name": "performance_audit", "args": {}, "id": "forced_performance"},
        ],
    )


def supervisor_node(state: dict) -> dict:
    """Route the submission, or pass through once the audits are in."""
    messages = state.get("messages") or []

    if not messages:
        source_code = state.get("source_code", "")
        language = state.get("language", "python")

        forced = state.get("force_full_audit") or looks_high_stakes(source_code)
        if forced:
            reason = (
                "caller requested a forced full audit"
                if state.get("force_full_audit")
                else "input matched the high-stakes heuristic (auth/database/exec surface)"
            )
            return {
                "messages": [_forced_fan_out()],
                "logs": [f"Supervisor: routing bypassed — {reason}."],
            }

        llm = get_llm(temperature=0.0).bind_tools(TOOLS)
        response = llm.invoke(
            [
                SystemMessage(content=SYSTEM_PROMPT),
                HumanMessage(
                    content=(
                        f"Language: {language}\n\nSubmission:\n```{language}\n"
                        f"{source_code[:4000]}\n```"
                    )
                ),
            ]
        )
        chosen = [tc["name"] for tc in getattr(response, "tool_calls", [])] or ["none"]
        return {
            "messages": [response],
            "logs": [f"Supervisor: router selected {', '.join(chosen)}."],
        }

    # Tool results are already in state; the loop ends here.
    return {"logs": ["Supervisor: audits complete, handing off to patch generator."]}
