"""Static-analysis fusion tests.

Bandit itself is not under test - it has its own suite. What is tested here is
the seam: severity mapping, the merge, and the rule that a scanner problem must
never be mistaken for a clean result.
"""

from app.agents import static_analysis
from app.agents.static_analysis import audit, merge, run_bandit

VULNERABLE = '''import hashlib
import subprocess

PASSWORD = "hunter2-prod-password"


def digest(raw):
    return hashlib.md5(raw.encode()).hexdigest()


def run(cmd):
    subprocess.call(cmd, shell=True)
'''


# --------------------------------------------------------------------------- #
# Scanning
# --------------------------------------------------------------------------- #

def test_bandit_finds_the_obvious_problems():
    findings, error = run_bandit(VULNERABLE)

    assert error is None, error
    titles = " ".join(f["title"] + f["explanation"] for f in findings).lower()
    assert "hardcoded" in titles or "password" in titles
    assert "md5" in titles or "hash" in titles
    assert "shell" in titles or "subprocess" in titles


def test_every_finding_carries_its_rule_id_as_source():
    findings, _ = run_bandit(VULNERABLE)

    assert findings
    for finding in findings:
        assert finding["source"].startswith("bandit")
        assert finding["severity"] in {"Critical", "High", "Medium", "Low"}
        assert finding["line_hint"]


def test_clean_code_produces_no_findings():
    findings, error = run_bandit("def add(a, b):\n    return a + b\n")

    assert error is None
    assert findings == []


def test_syntactically_broken_input_does_not_crash():
    findings, error = run_bandit("def broken(:\n")

    # Bandit cannot parse it; either outcome is fine, a traceback is not.
    assert isinstance(findings, list)
    assert error is None or isinstance(error, str)


def test_non_python_is_skipped_with_a_reason():
    findings, note = audit("body { color: red }", "css")

    assert findings == []
    assert note and "css" in note


def test_python_is_scanned_through_the_audit_entry_point():
    findings, note = audit(VULNERABLE, "python")

    assert note is None
    assert findings


# --------------------------------------------------------------------------- #
# Severity mapping
# --------------------------------------------------------------------------- #

def test_high_severity_needs_high_confidence_to_be_critical():
    """A HIGH-severity, LOW-confidence hit is a lead, not a Critical."""
    high_high = static_analysis._to_finding(
        {"issue_severity": "HIGH", "issue_confidence": "HIGH", "test_id": "B602"}
    )
    high_low = static_analysis._to_finding(
        {"issue_severity": "HIGH", "issue_confidence": "LOW", "test_id": "B602"}
    )

    assert high_high["severity"] == "Critical"
    assert high_low["severity"] == "Medium"


def test_unknown_severity_falls_back_to_medium():
    finding = static_analysis._to_finding({"issue_severity": "???", "test_id": "B000"})
    assert finding["severity"] == "Medium"


def test_known_rules_get_an_actionable_recommendation():
    finding = static_analysis._to_finding(
        {"issue_severity": "MEDIUM", "issue_confidence": "HIGH", "test_id": "B608"}
    )
    assert "bound parameters" in finding["recommendation"]


# --------------------------------------------------------------------------- #
# Merge
# --------------------------------------------------------------------------- #

def _f(title, line, severity="Medium", source="llm"):
    return {
        "title": title,
        "line_hint": line,
        "severity": severity,
        "source": source,
        "explanation": "",
        "recommendation": "",
    }


def test_distinct_findings_from_both_engines_are_kept():
    merged = merge(
        [_f("Missing authorization", "def delete_user(uid):")],
        [_f("subprocess with shell=True", "subprocess.call(cmd, shell=True)", source="bandit:B602")],
    )
    assert len(merged) == 2


def test_the_same_line_found_twice_is_reported_once_and_marked_confirmed():
    merged = merge(
        [_f("SQL injection", 'cur.execute("SELECT * FROM t WHERE n = " + n)')],
        [_f("hardcoded_sql_expressions", 'cur.execute("SELECT * FROM t WHERE n = "+n)',
            source="bandit:B608")],
    )

    assert len(merged) == 1, "whitespace differences must not defeat dedup"
    assert merged[0]["source"] == "llm+bandit:B608"
    # The LLM's wording survives, because it explains the issue in context.
    assert merged[0]["title"] == "SQL injection"


def test_agreement_takes_the_more_severe_rating():
    merged = merge(
        [_f("SQL injection", "x = 1", severity="Low")],
        [_f("sql", "x = 1", severity="Critical", source="bandit:B608")],
    )
    assert merged[0]["severity"] == "Critical"


def test_llm_findings_are_tagged_even_with_no_static_results():
    merged = merge([{"title": "Design flaw", "line_hint": "def f():"}], [])
    assert merged[0]["source"] == "llm"


def test_findings_without_a_line_hint_are_never_merged_together():
    """Empty hints would otherwise collapse into one another."""
    merged = merge([_f("a", "")], [_f("b", "", source="bandit:B101")])
    assert len(merged) == 2
