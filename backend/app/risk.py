"""Risk score — one number a reviewer can triage on.

Roadmap item 2c (docs/TECHNICAL_SPEC.md §7). No new dependency: the inputs are
findings the graph already has and the size of the reviewed code.

Three properties this scoring has to hold, in order of importance:

1. **An incomplete review can never look safe.** If an audit failed, the finding
   list is not evidence of anything, and a score computed from it would say
   "3/100, ship it" about code nothing examined. The score is therefore marked
   ``incomplete`` and carries no band — the same rule that governs the report
   (see :func:`app.graph.collect_node`). This is the single most important line
   in the module.
2. **Findings dominate; size only modulates.** A large diff is harder to review
   and so slightly riskier, but a 2000-line diff with nothing wrong in it is not
   more dangerous than a 5-line diff with a SQL injection. Size is capped at a
   +25% modifier so it can never manufacture risk on its own.
3. **Corroboration counts.** A finding both the LLM and the static analyser
   flagged independently is far less likely to be a hallucination, so it is
   weighted higher than either engine alone.
"""

from __future__ import annotations

from typing import Any, Literal, TypedDict

from .state import Finding

Band = Literal["none", "low", "medium", "high", "critical"]

# Chosen so that a single Critical finding (40) lands in "high" and two land in
# "critical" - i.e. one confirmed remote-exploit finding is enough to stop a
# merge, which is the behaviour the Check Run gate (item 2e) will want.
_WEIGHTS: dict[str, int] = {
    "Critical": 40,
    "High": 20,
    "Medium": 7,
    "Low": 2,
}

# A finding two independent engines agree on is materially more likely to be
# real. Deliberately modest: corroboration raises confidence, it does not change
# what the issue is.
_CONFIRMED_MULTIPLIER = 1.25

_MAX_SIZE_MODIFIER = 0.25
_SIZE_SATURATION_LINES = 2000

_BANDS: list[tuple[int, Band]] = [
    (75, "critical"),
    (50, "high"),
    (25, "medium"),
    (1, "low"),
    (0, "none"),
]


class RiskScore(TypedDict):
    score: int
    band: Band | Literal["unknown"]
    complete: bool
    size_modifier: float
    drivers: list[str]
    note: str


def _is_confirmed(finding: Finding) -> bool:
    return str(finding.get("source", "")).startswith("llm+")


def _size_modifier(source_code: str) -> float:
    """A mild multiplier for how much code was reviewed.

    Saturates at +25%: review quality does fall with diff size, but not enough
    to outweigh what was actually found.
    """
    lines = len([line for line in (source_code or "").splitlines() if line.strip()])
    return 1.0 + min(_MAX_SIZE_MODIFIER, lines / _SIZE_SATURATION_LINES)


def _band_for(score: int) -> Band:
    for threshold, band in _BANDS:
        if score >= threshold:
            return band
    return "none"


def score(
    security_issues: list[Finding],
    performance_issues: list[Finding],
    source_code: str = "",
    failed_audits: list[str] | None = None,
) -> RiskScore:
    """Compute the review's risk score.

    Performance findings contribute at a discount: a slow query is a cost, a SQL
    injection is a breach, and a score that let three ``Medium`` performance
    notes outrank one ``Critical`` vulnerability would be actively misleading to
    whoever triages on it.
    """
    failed = failed_audits or []
    modifier = _size_modifier(source_code)

    total = 0.0
    drivers: list[str] = []

    for finding in security_issues:
        weight = _WEIGHTS.get(str(finding.get("severity")), _WEIGHTS["Medium"])
        if _is_confirmed(finding):
            weight = weight * _CONFIRMED_MULTIPLIER
        total += weight

    for finding in performance_issues:
        total += _WEIGHTS.get(str(finding.get("severity")), _WEIGHTS["Medium"]) * 0.4

    raw = min(100, round(total * modifier))

    # Drivers: what a reader should look at first, most severe first.
    for finding in security_issues[:3]:
        label = f"{finding.get('severity', 'Medium')} security: {finding.get('title', 'finding')}"
        if _is_confirmed(finding):
            label += " (confirmed by static analysis)"
        drivers.append(label)
    if not security_issues:
        for finding in performance_issues[:2]:
            drivers.append(
                f"{finding.get('severity', 'Medium')} performance: "
                f"{finding.get('title', 'finding')}"
            )

    if failed:
        # The score is computed from findings that were never collected. Saying
        # "low risk" here would be the silent-pass bug wearing a number.
        return {
            "score": raw,
            "band": "unknown",
            "complete": False,
            "size_modifier": round(modifier, 2),
            "drivers": drivers,
            "note": (
                f"{', '.join(failed)} did not run, so this score is not a measure "
                "of risk - treat the review as incomplete."
            ),
        }

    band = _band_for(raw)
    return {
        "score": raw,
        "band": band,
        "complete": True,
        "size_modifier": round(modifier, 2),
        "drivers": drivers,
        "note": _NOTES[band],
    }


_NOTES: dict[Band, str] = {
    "none": "No issues found in what was audited.",
    "low": "Minor issues only; safe to merge after a glance.",
    "medium": "Worth a careful look before merging.",
    "high": "Serious issues found; do not merge without addressing them.",
    "critical": "Critical issues found; this should block the merge.",
}


def describe(result: dict[str, Any]) -> str:
    """One-line human summary, used in the report and the PR comment."""
    if not result.get("complete", True):
        return f"Risk score: unavailable ({result.get('note', 'review incomplete')})"
    return f"Risk score: {result.get('score', 0)}/100 ({result.get('band', 'none')})"
