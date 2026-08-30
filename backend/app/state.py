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
from typing import Annotated, Any, Literal, TypedDict

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

    force_full_audit: bool
    logs: Annotated[list[str], operator.add]
