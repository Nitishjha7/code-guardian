"""The graph's shared state.

``messages`` carries the supervisor's tool-calling history; ``force_full_audit``
bypasses the router and runs both auditors unconditionally.
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
    # "llm", "bandit:B608", or "llm+bandit:B608" when both found it independently
    source: str
    # Performance agent only:
    complexity_before: str
    complexity_after: str
    # Precedent from app/memory/ if this finding has been seen on this code shape
    # before. Empty string when memory is off or nothing matched.
    memory_note: str


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

    # Invoked but produced no result (bad key, dead model, rate limit). Separate
    # from "audited and found nothing" so a failed audit is never rendered as a
    # clean pass.
    failed_audits: list[str]
    audit_errors: list[str]

    risk: dict[str, Any]

    generated_tests: str
    tests_note: str

    force_full_audit: bool
    logs: Annotated[list[str], operator.add]

    token_usage: dict[str, Any]

    # PullRequestRef.repo_full_name on the webhook path, empty for an ad-hoc
    # /api/review call. Scopes long-term memory; absence just means no
    # preferences apply.
    repo_id: str
