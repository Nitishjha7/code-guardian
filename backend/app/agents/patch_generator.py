"""Patch Generator — synthesizes both audits into a fix.

Deliverable per docs/TECHNICAL_SPEC.md §4: a full refactored code block plus a
unified git diff, without altering the original business logic.

The model is asked only for the *rewritten file*. The unified diff is then
computed locally with ``difflib``. Asking an LLM to emit a valid unified diff —
correct hunk headers, correct line counts — is a well-known way to produce
patches that will not apply; deriving it from the two texts is exact by
construction and costs nothing.
"""

from __future__ import annotations

import difflib
import json

from langchain_core.messages import HumanMessage, SystemMessage

from ..config import get_llm
from ..state import Finding
from ._common import strip_code_fence, truncate

SYSTEM_PROMPT = """You are a senior engineer applying review feedback to code.

You are given the original source and a list of findings from a security audit
and a performance audit. Produce the corrected source file.

Hard rules:
- Preserve the original business logic, public API, function names and
  signatures. You are fixing defects, not redesigning.
- Fix every finding you can fix safely. If a finding cannot be fixed without
  changing behaviour or without context you do not have, leave the code as-is
  and add a brief `TODO(code-guardian):` comment on the relevant line.
- Never invent new dependencies unless a fix strictly requires one.
- Never hardcode a secret. Where a secret was hardcoded, read it from an
  environment variable instead.
- Keep the original formatting and comment style.

Output the complete corrected file inside a single fenced code block, and
nothing else — no explanation before or after."""


def _format_findings(security: list[Finding], performance: list[Finding]) -> str:
    if not security and not performance:
        return "No findings were reported."
    payload = {
        "security_findings": security,
        "performance_findings": performance,
    }
    return json.dumps(payload, indent=2)


def make_unified_diff(original: str, fixed: str, filename: str = "source") -> str:
    """Exact unified diff between the original and the patched source."""
    if not fixed or fixed.strip() == original.strip():
        return ""
    diff = difflib.unified_diff(
        original.splitlines(keepends=True),
        fixed.splitlines(keepends=True),
        fromfile=f"a/{filename}",
        tofile=f"b/{filename}",
        n=3,
    )
    return "".join(diff)


def generate(
    source_code: str,
    language: str,
    security_issues: list[Finding],
    performance_issues: list[Finding],
    filename: str = "source",
) -> tuple[str, str]:
    """Return ``(fixed_code, unified_diff)``.

    When there is nothing to fix, returns the original code and an empty diff
    rather than burning a call on a no-op rewrite.
    """
    if not security_issues and not performance_issues:
        return source_code, ""

    llm = get_llm(temperature=0.0)
    response = llm.invoke(
        [
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(
                content=(
                    f"Language: {language}\n\n"
                    f"Findings to address:\n{_format_findings(security_issues, performance_issues)}\n\n"
                    f"Original source:\n```{language}\n{truncate(source_code)}\n```"
                )
            ),
        ]
    )
    fixed_code = strip_code_fence(str(response.content))
    if not fixed_code:
        return source_code, ""
    return fixed_code, make_unified_diff(source_code, fixed_code, filename)
