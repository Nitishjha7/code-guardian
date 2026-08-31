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
3. ``looks_high_stakes`` — a cheap static backstop that flips the override on
   when the input obviously touches an auth or DB surface, so the recall risk
   does not depend solely on the caller remembering to set the flag.
"""

from __future__ import annotations

import json
import re
from contextvars import ContextVar

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.tools import tool

from ..config import get_llm
from . import performance_agent, security_agent

# Set by the graph before each run so the tools can see the code without the
# supervisor having to echo an entire diff back through its own tool arguments
# (which would cost the input tokens twice and risk the model truncating it).
#
# A ContextVar rather than a plain module global: the API serves concurrent
# requests, and a global dict would let two simultaneous reviews audit each
# other's code. ContextVars are copied into the context LangGraph runs each node
# in, so every review sees its own submission.
_CURRENT_INPUT: ContextVar[tuple[str, str]] = ContextVar(
    "code_guardian_current_input", default=("", "python")
)


def set_current_input(source_code: str, language: str) -> None:
    _CURRENT_INPUT.set((source_code, language))


def _run_audit(name: str, audit_fn) -> str:
    """Run one specialist and wrap the result in a success/failure envelope.

    The envelope exists because of the worst bug this system can have: if an
    audit raises (bad API key, decommissioned model, rate limit) and that is
    silently turned into "no findings", the review reports **clean code** on
    code it never actually looked at. A bare JSON array cannot distinguish
    "audited, found nothing" from "never ran", so every audit reports which of
    the two happened and the graph refuses to render a failed audit as a pass.
    """
    source_code, language = _CURRENT_INPUT.get()
    try:
        findings = audit_fn(source_code, language)
        return json.dumps({"ok": True, "findings": findings})
    except Exception as exc:  # noqa: BLE001 - the failure must reach the report
        return json.dumps({"ok": False, "error": f"{type(exc).__name__}: {exc}"})


@tool
def security_audit() -> str:
    """Audit the submitted code for security defects.

    Call this when the code does any of: handle user input, build SQL or shell
    commands, authenticate or authorize a request, read or write files or
    network resources, deserialize data, use cryptography, or contain anything
    that looks like a credential.

    Do NOT call this for pure styling (CSS), pure formatting changes, static
    copy or markup with no data handling, or comment-only edits.

    Returns a JSON envelope with the findings and their severity ratings.
    """
    return _run_audit("security", security_agent.audit)


@tool
def performance_audit() -> str:
    """Audit the submitted code for runtime and resource cost.

    Call this whenever the code contains ANY of the following, even if it also
    has a security problem - the two audits are independent and both should run:
      - a loop, comprehension, `.map`/`.filter`/`.forEach`, or recursion
      - a loop or comprehension nested inside another, or a lookup performed
        inside a loop (including a query, `.filter()` or `.find()` per item)
      - building a string, list or dict incrementally across iterations
      - opening a file, socket, cursor or connection
      - a database or network call of any kind
      - sorting, or any operation whose cost grows with the size of the input

    Do NOT call this for pure configuration files, static markup, styling,
    declarative data, or straight-line code with no loop, no I/O and no
    collection processing.

    Returns a JSON envelope with the findings and Big-O before/after where
    applicable.
    """
    return _run_audit("performance", performance_agent.audit)


TOOLS = [security_audit, performance_audit]
TOOLS_BY_NAME = {t.name: t for t in TOOLS}

SYSTEM_PROMPT = """You are the supervisor of a code review system. You do not \
review code yourself — you decide which specialist auditors a submission needs, \
then stop.

You have two auditors available as tools. Read their descriptions as routing
criteria and call every tool whose criteria the submission meets — one, both, or
neither. Call them in a single turn so they run in parallel.

The auditors are independent. Code that has a security problem very often also
has a performance problem; finding one is never a reason to skip the other. Judge
each tool's criteria on its own and call both when both are met.

Bias: when you are genuinely unsure whether a tool's criteria are met, call it.
A missed vulnerability costs far more than a wasted audit.

Once the tool results are back, do not call anything else and do not summarise
the findings. Reply with a single short sentence naming which auditors you ran
and why. Another node handles the report."""

# Identifier-shaped terms. The boundaries are lookarounds rather than ``\b``
# because ``\b`` does not fire between an underscore and a letter, which would
# miss exactly the names real code uses: DB_PASSWORD, check_password, api_key.
_HIGH_STAKES_TERMS = re.compile(
    r"(?<![A-Za-z0-9])(?:"
    r"password|passwd|pwd|secret|token|api[_-]?key|apikey|credential|auth|"
    r"login|signin|session|jwt|oauth|permission|role|admin|sql|cursor|query|"
    r"execute|database|subprocess|eval|exec|pickle|deserialize|hashlib"
    r")(?![A-Za-z0-9])",
    re.IGNORECASE,
)

# Phrase- and symbol-shaped patterns, which cannot carry the same boundaries.
_HIGH_STAKES_PHRASES = re.compile(
    r"select\s+.+?\bfrom\b|insert\s+into|update\s+.+?\bset\b|delete\s+from|"
    r"\bdb\.|os\.system|os\.popen|\.raw\(|request\.(?:args|form|json|body)",
    re.IGNORECASE | re.DOTALL,
)


def looks_high_stakes(source_code: str) -> bool:
    """Cheap static backstop for the router's recall risk.

    Deliberately over-inclusive: a false positive here costs one extra audit,
    a false negative costs a missed vulnerability.
    """
    text = source_code or ""
    return bool(_HIGH_STAKES_TERMS.search(text) or _HIGH_STAKES_PHRASES.search(text))


def _forced_fan_out() -> AIMessage:
    """Hand-built tool calls that bypass the router entirely."""
    return AIMessage(
        content="",
        tool_calls=[
            {"name": "security_audit", "args": {}, "id": "forced_security"},
            {"name": "performance_audit", "args": {}, "id": "forced_performance"},
        ],
    )


def route_with_llm(source_code: str, language: str) -> AIMessage:
    """The router's decision on its own, with no backstop applied.

    Split out from :func:`supervisor_node` so the routing eval can measure the
    *model's* judgement in isolation. Measuring only the shipped path would
    flatter the router, because the high-stakes backstop catches many of the
    cases the model would otherwise miss.
    """
    llm = get_llm(temperature=0.0).bind_tools(TOOLS)
    return llm.invoke(
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

        response = route_with_llm(source_code, language)
        chosen = [tc["name"] for tc in getattr(response, "tool_calls", [])] or ["none"]
        return {
            "messages": [response],
            "logs": [f"Supervisor: router selected {', '.join(chosen)}."],
        }

    # Tool results are already in state; the loop ends here.
    return {"logs": ["Supervisor: audits complete, handing off to patch generator."]}
