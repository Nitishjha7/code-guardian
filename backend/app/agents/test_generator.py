"""Test Generation Agent — a regression test per finding.

Roadmap item 2d (docs/TECHNICAL_SPEC.md §7).

**Generation-only: nothing here executes what it writes.** Running LLM-authored
tests safely needs a sandbox (no network, escape-proof filesystem, hard timeout)
— an infrastructure project, not a review-agent feature.

A node, not the `@tool` the spec sketched: §3a says the model should own control
flow only where the decision needs judgement. "Which audits is this diff worth?"
does; "are there findings to test?" is a boolean over state the graph already
holds, and an `if` gets that right more often than a model can.
"""

from __future__ import annotations

from langchain_core.messages import HumanMessage, SystemMessage

from ..config import get_llm
from ..state import Finding
from ._common import strip_code_fence, truncate

# Only findings at or above these severities are worth a regression test. A Low
# "consider a constant here" note does not need one, and generating tests for
# every finding would bury the ones that matter.
WORTH_TESTING = {"Critical", "High"}

# Language -> the framework a reviewer would actually reach for.
_FRAMEWORKS: dict[str, str] = {
    "python": "pytest",
    "javascript": "Jest (describe/it/expect)",
    "typescript": "Jest with TypeScript (describe/it/expect)",
    "java": "JUnit 5",
    "go": "the standard `testing` package",
    "ruby": "RSpec",
    "php": "PHPUnit",
    "csharp": "xUnit",
    "rust": "the built-in `#[test]` harness",
    "kotlin": "JUnit 5",
}

SYSTEM_PROMPT = """You are a senior engineer writing regression tests for \
defects found in a code review.

For each finding you are given, write ONE test that **fails against the original
code and passes once the defect is fixed**. That is the whole point: a test that
passes either way proves nothing.

Rules:
- Write tests only for the findings supplied. Do not invent additional cases.
- Name each test after the defect, e.g. `test_username_is_not_interpolated_into_sql`.
- Above each test, add a one-line comment naming the finding it pins down.
- Prefer asserting on observable behaviour (the query that is executed, the
  hash algorithm used, the exception raised) over asserting on implementation
  details that a valid fix might legitimately change.
- Where a test needs a fixture, stub or fake, define it inline. Assume nothing
  about the surrounding project layout.
- If a finding genuinely cannot be tested without infrastructure you were not
  given (a live database, a network peer), write the test with the setup you
  would need and mark it skipped, with a comment saying what is missing. Do not
  silently omit it.

Output only the test file, inside a single fenced code block. No prose."""


def _format_findings(findings: list[Finding]) -> str:
    lines = []
    for i, finding in enumerate(findings, start=1):
        lines.append(
            f"{i}. [{finding.get('severity', 'Medium')}] {finding.get('title', 'finding')}\n"
            f"   where: {finding.get('line_hint', 'n/a')}\n"
            f"   why:   {finding.get('explanation', 'n/a')}\n"
            f"   fix:   {finding.get('recommendation', 'n/a')}"
        )
    return "\n".join(lines)


def worth_testing(
    security_issues: list[Finding], performance_issues: list[Finding]
) -> list[Finding]:
    """Select the findings a regression test would actually pin down.

    Security findings only. A performance regression needs a benchmark with a
    threshold, and a threshold picked by an LLM with no machine to measure on is
    a flaky test waiting to happen - worse than no test, because it trains the
    team to ignore red.
    """
    return [f for f in security_issues if f.get("severity") in WORTH_TESTING]


def generate(
    source_code: str,
    language: str,
    findings: list[Finding],
) -> tuple[str, str | None]:
    """Return ``(test_code, note)``. ``note`` explains an empty result."""
    if not findings:
        return "", "no Critical or High security findings to write tests for"

    framework = _FRAMEWORKS.get(language.lower())
    if framework is None:
        return "", f"no test framework configured for {language}"

    llm = get_llm(temperature=0.0)
    response = llm.invoke(
        [
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(
                content=(
                    f"Language: {language}\nTest framework: {framework}\n\n"
                    f"Findings to pin down:\n{_format_findings(findings)}\n\n"
                    f"Code under review:\n```{language}\n{truncate(source_code)}\n```"
                )
            ),
        ]
    )
    tests = strip_code_fence(str(response.content))
    if not tests.strip():
        return "", "the model returned no test code"
    return tests, None
