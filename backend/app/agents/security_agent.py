"""Security Agent — OWASP-focused auditor.

Deliverable per docs/TECHNICAL_SPEC.md §4: a categorised vulnerability list with
severity ratings.
"""

from __future__ import annotations

import logging

from langchain_core.messages import HumanMessage, SystemMessage

from ..config import get_llm
from ..state import Finding
from . import static_analysis
from ._common import parse_json_list, truncate

logger = logging.getLogger("code_guardian.security_agent")

SYSTEM_PROMPT = """You are a senior application security engineer performing a \
code audit. You look for real, exploitable defects — not style opinions.

Audit specifically for:
- OWASP Top 10: injection (SQL/NoSQL/command/LDAP), broken access control,
  broken authentication, SSRF, XSS, insecure design.
- Hardcoded secrets: API keys, passwords, tokens, private keys, connection
  strings committed in source.
- Insecure deserialization (pickle, yaml.load, eval, exec on untrusted input).
- Weak or missing cryptography: MD5/SHA1 for passwords, ECB mode, static IVs,
  missing TLS verification.
- Unsafe input handling: path traversal, unvalidated redirects, missing
  authorization checks on privileged operations.

Rules:
- Report only issues you can point to in the supplied code. Do not speculate
  about code you cannot see.
- If the code has no security defects, return an empty array. An empty array is
  a valid and often correct answer; do not invent findings to seem thorough.
- Severity: Critical = remotely exploitable with serious impact; High = directly
  exploitable; Medium = requires unusual preconditions; Low = defence in depth.

Reply with a JSON array only. No prose before or after. Each element:
{
  "title": "short issue name",
  "severity": "Critical" | "High" | "Medium" | "Low",
  "line_hint": "the offending line or function name, quoted from the input",
  "explanation": "why this is exploitable, concretely",
  "recommendation": "the specific fix"
}"""


def audit(source_code: str, language: str) -> list[Finding]:
    """Run the security audit: LLM judgement fused with static analysis.

    Both engines run and their findings are merged (see
    :mod:`app.agents.static_analysis` for why neither subsumes the other). The
    LLM half is the one that can fail hard - a scanner that is missing or
    unsupported for this language only means fewer findings, not a broken audit,
    so its failure is attached as a note rather than raised.
    """
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
        finding.setdefault("source", "llm")

    static_findings, note = static_analysis.audit(source_code, language)
    if note:
        logger.info("Static analysis contributed nothing: %s", note)

    return static_analysis.merge(findings, static_findings)  # type: ignore[arg-type]
