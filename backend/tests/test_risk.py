"""Risk score tests.

The score is what item 2e will gate merges on, so its ordering properties
matter more than its exact arithmetic. These tests pin the properties.
"""

from app.risk import describe, score


def _sec(severity, title="finding", source="llm"):
    return {"severity": severity, "title": title, "source": source}


def _perf(severity, title="slow"):
    return {"severity": severity, "title": title, "source": "llm"}


# --------------------------------------------------------------------------- #
# The rule that matters most
# --------------------------------------------------------------------------- #

def test_a_failed_audit_never_produces_a_reassuring_score():
    """The silent-pass bug must not come back wearing a number.

    A failed security audit yields no findings, and a score computed from no
    findings would read "0/100, none" about code nothing examined.
    """
    result = score([], [], "x = 1", failed_audits=["security_audit"])

    assert result["complete"] is False
    assert result["band"] == "unknown"
    assert "did not run" in result["note"]
    assert "unavailable" in describe(result)


def test_a_complete_review_with_no_findings_is_a_real_zero():
    result = score([], [], "def add(a, b):\n    return a + b\n")

    assert result["complete"] is True
    assert result["score"] == 0
    assert result["band"] == "none"


# --------------------------------------------------------------------------- #
# Ordering
# --------------------------------------------------------------------------- #

def test_severity_ordering_is_respected():
    critical = score([_sec("Critical")], [], "")["score"]
    high = score([_sec("High")], [], "")["score"]
    medium = score([_sec("Medium")], [], "")["score"]
    low = score([_sec("Low")], [], "")["score"]

    assert critical > high > medium > low > 0


def test_one_critical_finding_is_at_least_high_band():
    """Item 2e will block merges on this; one Critical has to be enough."""
    assert score([_sec("Critical")], [], "")["band"] in {"high", "critical"}


def test_two_criticals_reach_the_critical_band():
    assert score([_sec("Critical"), _sec("Critical")], [], "")["band"] == "critical"


def test_a_critical_vulnerability_outranks_several_medium_slowdowns():
    """A slow query is a cost; a SQL injection is a breach."""
    vulnerable = score([_sec("Critical")], [], "")["score"]
    slow = score([], [_perf("Medium")] * 3, "")["score"]

    assert vulnerable > slow


def test_performance_findings_are_discounted_against_security():
    sec = score([_sec("High")], [], "")["score"]
    perf = score([], [_perf("High")], "")["score"]

    assert perf < sec


# --------------------------------------------------------------------------- #
# Corroboration
# --------------------------------------------------------------------------- #

def test_a_confirmed_finding_outweighs_a_single_engine_one():
    confirmed = score([_sec("High", source="llm+bandit:B608")], [], "")["score"]
    single = score([_sec("High")], [], "")["score"]

    assert confirmed > single


def test_confirmation_is_noted_in_the_drivers():
    result = score([_sec("Critical", "SQLi", source="llm+bandit:B608")], [], "")
    assert "confirmed by static analysis" in result["drivers"][0]


# --------------------------------------------------------------------------- #
# Size modifier
# --------------------------------------------------------------------------- #

def test_size_cannot_manufacture_risk_on_its_own():
    """A 2000-line clean diff is still a zero."""
    result = score([], [], "x = 1\n" * 2000)
    assert result["score"] == 0


def test_size_only_modulates_within_its_cap():
    small = score([_sec("Medium")], [], "x = 1\n")
    huge = score([_sec("Medium")], [], "x = 1\n" * 5000)

    assert huge["score"] >= small["score"]
    assert huge["size_modifier"] <= 1.25


def test_blank_lines_do_not_count_toward_size():
    dense = score([_sec("Medium")], [], "x = 1\n" * 100)
    padded = score([_sec("Medium")], [], "x = 1\n\n\n" * 100)

    assert dense["size_modifier"] == padded["size_modifier"]


# --------------------------------------------------------------------------- #
# Bounds and reporting
# --------------------------------------------------------------------------- #

def test_score_is_capped_at_100():
    result = score([_sec("Critical")] * 20, [_perf("Critical")] * 20, "x = 1\n" * 3000)
    assert result["score"] == 100


def test_drivers_lead_with_security_and_stay_short():
    result = score(
        [_sec("Critical", "SQLi"), _sec("High", "secret"), _sec("Low", "a"), _sec("Low", "b")],
        [_perf("High", "N+1")],
        "",
    )

    assert len(result["drivers"]) == 3
    assert "SQLi" in result["drivers"][0]
    assert all("performance" not in d for d in result["drivers"])


def test_performance_drives_the_summary_when_there_is_no_security_finding():
    result = score([], [_perf("High", "N+1 query")], "")
    assert "N+1 query" in result["drivers"][0]


def test_describe_is_one_readable_line():
    assert describe(score([_sec("Critical")], [], "")).startswith("Risk score: ")
