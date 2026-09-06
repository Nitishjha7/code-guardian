"""The graph's shared state.

This mirrors ``ReviewerState`` in docs/TECHNICAL_SPEC.md, with two additions the
spec's sketch left implicit:

* ``messages`` — the supervisor is a tool-calling loop, so it needs a message
  history with the standard ``add_messages`` reducer.
* ``force_full_audit`` — the "high-stakes override" mitigation from §3a. When
  true the router is bypassed and both auditors are run unconditionally.
"""

from __future__ import annotations

import operator
from typing import Any, Literal

# TypedDict comes from typing_extensions, not typing: pydantic (which validates
# the graph state) rejects typing.TypedDict on Python < 3.12, and the backend
# image targets 3.11.
from typing_extensions import Annotated, TypedDict

from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages

Severity = Literal["Critical", "High", "Medium", "Low"]


class Finding(TypedDict, total=False):
    """One issue reported by a specialist agent."""

    title: str
    severity: Severity
    line_hint: str
    explanation: str
    recommendation: str
    # Which engine produced this: "llm", "bandit:B608", or "llm+bandit:B608"
    # when both found it independently.
    source: str
    # Performance agent only:
    complexity_before: str
    complexity_after: str


class ReviewerState(TypedDict, total=False):
    source_code: str
    language: str

    messages: Annotated[list[AnyMessage], add_messages]

    security_issues: list[Finding]
    performance_issues: list[Finding]

    fixed_code: str
    diff: str
    summary_report: str

    guardrail_report: dict[str, Any]
    routed_to: list[str]

    # Audits that were invoked but never produced a result (bad key, dead model,
    # rate limit). Kept separate from "audited and found nothing" so that a
    # failed audit can never be rendered as a clean pass.
    failed_audits: list[str]
    audit_errors: list[str]

    # Weighted risk score computed once in collect_node - see app/risk.py.
    # Marked incomplete rather than low when an audit failed.
    risk: dict[str, Any]

    # Audits that were invoked but never produced a result (bad key, dead model,
    # rate limit). Kept separate from "found nothing" so a failed audit can never
    # be rendered as a clean pass.
    failed_audits: list[str]
    audit_errors: list[str]

    force_full_audit: bool
    logs: Annotated[list[str], operator.add]
