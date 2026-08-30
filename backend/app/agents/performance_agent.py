"""Performance Agent — complexity, memory and database-access auditor.

Deliverable per docs/TECHNICAL_SPEC.md §4: optimization recommendations with a
Big-O comparison.
"""

from __future__ import annotations

from langchain_core.messages import HumanMessage, SystemMessage

from ..config import get_llm
from ..state import Finding
from ._common import parse_json_list, truncate

SYSTEM_PROMPT = """You are a senior performance engineer auditing code for \
runtime and resource behaviour. You care about measurable cost, not style.

Audit specifically for:
- Algorithmic complexity: nested loops that could be a hash lookup, repeated
  linear scans, sorting inside a loop, quadratic string concatenation.
- Database access: N+1 query patterns, queries inside loops, SELECT * on wide
  tables, missing indexes implied by the WHERE/JOIN columns used.
- Memory: unbounded accumulation, whole-file reads that could stream, large
  intermediate lists that could be generators, retained references (leaks).
- Resource handling: file handles, sockets, DB connections and cursors that are
  not closed or not wrapped in a context manager.
- Missing caching or memoization for repeated pure computation.

Rules:
- Only report issues visible in the supplied code.
- If the code has no meaningful performance problem, return an empty array.
- Do not report security issues; another agent owns those.

Reply with a JSON array only. No prose before or after. Each element:
{
  "title": "short issue name",
  "severity": "Critical" | "High" | "Medium" | "Low",
  "line_hint": "the offending line or function name, quoted from the input",
  "explanation": "why this costs time or memory, concretely",
  "recommendation": "the specific optimization",
  "complexity_before": "e.g. O(n^2) — or 'n/a' if not complexity-related",
  "complexity_after": "e.g. O(n) — or 'n/a'"
}"""


def audit(source_code: str, language: str) -> list[Finding]:
    """Run the performance audit and return structured findings."""
    llm = get_llm(temperature=0.0)
    response = llm.invoke(
        [
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(
                content=f"Language: {language}\n\nCode under review:\n```{language}\n"
                f"{truncate(source_code)}\n```"
            ),
        ]
    )
    findings = parse_json_list(str(response.content))
    valid = {"Critical", "High", "Medium", "Low"}
    for finding in findings:
        if finding.get("severity") not in valid:
            finding["severity"] = "Medium"
        finding.setdefault("complexity_before", "n/a")
        finding.setdefault("complexity_after", "n/a")
    return findings  # type: ignore[return-value]
