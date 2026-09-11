"""Deterministic static analysis, fused into the security audit.

Neither engine subsumes the other, which is the whole argument (spec §7):

* Bandit cannot miss a pattern it has a rule for, and cannot hallucinate one it
  does not.
* The LLM catches what no rule encodes - missing authorization, business-logic
  flaws - and explains why in context.

So both run and their findings merge into one list, tagged with ``source``.

Bandit is Python-only; elsewhere this is a no-op and the report says so. Semgrep
would be one more ``_run_*`` function of the same shape.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import tempfile

from ..state import Finding

logger = logging.getLogger("code_guardian.static_analysis")

SUPPORTED_LANGUAGES = {"python"}

# Bandit reports severity and confidence separately. A HIGH-severity finding the
# scanner is only LOW-confidence about is not a Critical - it is a lead. This
# table collapses the two axes the way a reviewer would triage them.
_SEVERITY_MATRIX: dict[tuple[str, str], str] = {
    ("HIGH", "HIGH"): "Critical",
    ("HIGH", "MEDIUM"): "High",
    ("HIGH", "LOW"): "Medium",
    ("MEDIUM", "HIGH"): "High",
    ("MEDIUM", "MEDIUM"): "Medium",
    ("MEDIUM", "LOW"): "Low",
    ("LOW", "HIGH"): "Medium",
    ("LOW", "MEDIUM"): "Low",
    ("LOW", "LOW"): "Low",
}

# Bandit's own messages are terse and rule-shaped. These make the common ones
# read like review comments; anything without an entry falls back to Bandit's
# text, which is always better than nothing.
_RECOMMENDATIONS: dict[str, str] = {
    "B105": "Do not hardcode credentials. Read them from an environment variable or a secrets manager.",
    "B106": "Do not pass a hardcoded password as an argument. Read it from the environment.",
    "B107": "Remove the hardcoded password default; require it to be supplied.",
    "B108": "Use `tempfile.mkstemp()` or `tempfile.TemporaryDirectory()` instead of a predictable /tmp path.",
    "B301": "Do not unpickle untrusted data. Use JSON, or sign the payload and verify before loading.",
    "B303": "Replace MD5/SHA1 with SHA-256, or with bcrypt/argon2 for passwords.",
    "B304": "Replace this insecure cipher with AES-GCM.",
    "B305": "Do not use ECB mode; use an authenticated mode such as GCM.",
    "B306": "Replace `mktemp()` with `mkstemp()`.",
    "B307": "Do not call `eval()` on input you do not fully control. Use `ast.literal_eval()` or an explicit parser.",
    "B308": "Escape the value instead of marking it safe.",
    "B310": "Validate the URL scheme before opening it, to prevent `file://` and SSRF.",
    "B321": "FTP is unencrypted. Use SFTP or HTTPS.",
    "B324": "Use a secure hash (SHA-256+), or pass `usedforsecurity=False` if this hash is not security-relevant.",
    "B501": "Do not disable TLS certificate verification.",
    "B506": "Use `yaml.safe_load()` instead of `yaml.load()`.",
    "B601": "Avoid shell parameter expansion; pass arguments as a list.",
    "B602": "Do not use `shell=True` with untrusted input. Pass the command as a list.",
    "B603": "Validate the arguments before passing them to a subprocess.",
    "B604": "Do not pass a shell command built from untrusted input.",
    "B605": "Replace `os.system()` with `subprocess.run([...])` and a list of arguments.",
    "B608": "Build SQL with bound parameters (`cursor.execute(sql, params)`), never string concatenation.",
    "B609": "Avoid wildcard arguments in shell commands.",
    "B701": "Enable autoescaping in the template environment.",
}


def is_available() -> bool:
    """Whether Bandit can be imported in this interpreter."""
    try:
        import bandit  # noqa: F401
    except Exception:
        return False
    return True


def _offending_line(code_block: str, line_number: object) -> str:
    """Pull the offending line out of Bandit's ``code`` field.

    Bandit returns a few lines of context, each prefixed with its line number:

        "2 \\n3 DB_PASSWORD = \\"hunter2\\"\\n4 \\n"

    Taking the first line therefore yields a neighbouring line - often a blank
    one - rather than the issue itself, which both misleads the reader and
    breaks deduplication against the LLM's quote of the real line.
    """
    target = str(line_number)
    fallback = ""
    for raw in (code_block or "").splitlines():
        number, _, rest = raw.partition(" ")
        if not number.strip().isdigit():
            continue
        text = rest.strip()
        if number.strip() == target:
            return text
        if text and not fallback:
            fallback = text
    return fallback


def _title_for(issue: dict) -> str:
    """A readable title.

    Bandit's ``test_name`` is a rule slug ("hashlib", "hardcoded_sql_expressions")
    that reads like debug output in a review. ``issue_text`` is a sentence
    written for a human, so that is used, with the slug kept only as a fallback.
    """
    text = str(issue.get("issue_text", "")).strip()
    if text:
        first = text.split(". ")[0].rstrip(".")
        return first if len(first) <= 110 else first[:107] + "..."
    return str(issue.get("test_name") or "Static analysis finding").replace("_", " ")


def _to_finding(issue: dict) -> Finding:
    severity = _SEVERITY_MATRIX.get(
        (
            str(issue.get("issue_severity", "MEDIUM")).upper(),
            str(issue.get("issue_confidence", "MEDIUM")).upper(),
        ),
        "Medium",
    )
    test_id = str(issue.get("test_id", ""))
    line_hint = _offending_line(issue.get("code") or "", issue.get("line_number"))

    return {
        "title": _title_for(issue),
        "severity": severity,
        "line_hint": line_hint or f"line {issue.get('line_number', '?')}",
        "explanation": str(issue.get("issue_text", "")),
        "recommendation": _RECOMMENDATIONS.get(
            test_id, "See Bandit rule " + test_id if test_id else "Review this pattern."
        ),
        "source": f"bandit:{test_id}" if test_id else "bandit",
    }


def run_bandit(source_code: str, timeout: int = 30) -> tuple[list[Finding], str | None]:
    """Scan Python source with Bandit.

    Returns ``(findings, error)``. Bandit performs AST analysis and never
    executes the code it scans, so running it on an untrusted submission is
    safe; the file is written to a private temp path and removed afterwards.

    A scanner failure returns an error string rather than raising: the LLM half
    of the audit may still have succeeded, and losing that to a missing optional
    dependency would be the wrong trade. The caller surfaces the error rather
    than dropping it.
    """
    if not is_available():
        return [], "bandit is not installed"

    handle, path = tempfile.mkstemp(suffix=".py", prefix="cg_scan_")
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as fh:
            fh.write(source_code)

        result = subprocess.run(
            [sys.executable, "-m", "bandit", "-f", "json", "-q", path],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        # Bandit exits 1 when it finds issues; that is a result, not a failure.
        # Only a missing/!=0-without-output run is an actual error.
        if not result.stdout.strip():
            return [], (result.stderr or "bandit produced no output").strip()[:300]

        payload = json.loads(result.stdout)
    except subprocess.TimeoutExpired:
        return [], f"bandit timed out after {timeout}s"
    except (json.JSONDecodeError, OSError) as exc:
        return [], f"bandit output could not be read: {exc}"
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass

    issues = payload.get("results") or []
    return [_to_finding(issue) for issue in issues], None


# Below this length a normalised line carries too little signal to match on -
# "x=1" or "return" would collide across unrelated findings.
_MIN_MATCH_LENGTH = 12


def _dedupe_key(finding: Finding) -> str:
    """Normalised code line, used to spot the same issue found twice."""
    return "".join((finding.get("line_hint") or "").split()).lower()


def _same_line(a: str, b: str) -> bool:
    """Whether two normalised hints refer to the same line of code.

    Containment rather than equality: the LLM quotes the expression it objects
    to (``hashlib.md5(raw).hexdigest() == stored``) while the scanner reports
    the whole statement (``return hashlib.md5(raw).hexdigest() == stored``).
    Requiring equality would leave every such pair reported twice.
    """
    if not a or not b:
        return False
    if len(a) < _MIN_MATCH_LENGTH or len(b) < _MIN_MATCH_LENGTH:
        return a == b
    return a in b or b in a


def merge(llm_findings: list[Finding], static_findings: list[Finding]) -> list[Finding]:
    """Combine both engines' findings, preferring the LLM's wording on overlap.

    When both flag the same line, the LLM's version is kept because it explains
    the issue in context, but the entry is re-tagged to record that the scanner
    independently confirmed it. A finding two independent engines agree on is
    the one a reviewer should read first, and hiding that agreement would throw
    away the most useful signal the fusion produces.
    """
    merged: list[Finding] = []
    indexed: list[tuple[str, Finding]] = []

    for finding in llm_findings:
        finding.setdefault("source", "llm")
        indexed.append((_dedupe_key(finding), finding))
        merged.append(finding)

    for finding in static_findings:
        key = _dedupe_key(finding)
        existing = next((f for k, f in indexed if _same_line(key, k)), None)
        if existing is not None:
            existing["source"] = f"llm+{finding.get('source', 'bandit')}"
            # Two engines agreeing outranks either one alone.
            if _rank(finding.get("severity")) < _rank(existing.get("severity")):
                existing["severity"] = finding["severity"]
            continue
        merged.append(finding)

    return merged


_ORDER = {"Critical": 0, "High": 1, "Medium": 2, "Low": 3}


def _rank(severity: object) -> int:
    return _ORDER.get(str(severity), 2)


def audit(source_code: str, language: str) -> tuple[list[Finding], str | None]:
    """Run every scanner that applies to ``language``.

    Returns ``(findings, note)`` where ``note`` explains why the scanner did not
    contribute, when it did not.
    """
    if language.lower() not in SUPPORTED_LANGUAGES:
        return [], f"no static analyser configured for {language}"
    return run_bandit(source_code)
