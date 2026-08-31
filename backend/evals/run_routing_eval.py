"""Measure the supervisor's routing quality against the labelled set.

    python -m evals.run_routing_eval              # both modes
    python -m evals.run_routing_eval --mode router-only
    python -m evals.run_routing_eval --min-security-recall 1.0

Two modes, because they answer different questions:

* ``router-only`` - the LLM's judgement alone. This is the number that tells you
  whether the tool docstrings are doing their job as routing criteria.
* ``as-shipped``  - router plus the ``looks_high_stakes`` backstop, i.e. what
  actually runs in production. This is the number that describes real risk.

Reporting only ``as-shipped`` would flatter the model (the backstop catches a lot
of what it misses); reporting only ``router-only`` would overstate real risk.

Exit code is non-zero when security recall falls below the threshold, so this can
gate a release the same way a test suite does. Recall is the gate and precision
is only reported, because the two errors are not symmetric: a false negative is a
missed vulnerability, a false positive is a few wasted cents.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass

from app.agents import supervisor
from evals.routing_cases import CASES, RoutingCase

MODES = ("router-only", "as-shipped")


@dataclass
class Outcome:
    case: RoutingCase
    security: bool
    performance: bool
    forced: bool = False
    error: str = ""


def decide(case: RoutingCase, mode: str) -> Outcome:
    """Run one case through the router (and the backstop, when as-shipped)."""
    if mode == "as-shipped" and supervisor.looks_high_stakes(case.code):
        return Outcome(case=case, security=True, performance=True, forced=True)

    try:
        response = supervisor.route_with_llm(case.code, case.language)
    except Exception as exc:  # noqa: BLE001
        return Outcome(case=case, security=False, performance=False, error=str(exc))

    called = {tc["name"] for tc in getattr(response, "tool_calls", [])}
    return Outcome(
        case=case,
        security="security_audit" in called,
        performance="performance_audit" in called,
    )


def _scores(outcomes: list[Outcome], attr: str) -> tuple[float, float, int, int]:
    """Return ``(recall, precision, false_negatives, false_positives)``."""
    tp = fn = fp = 0
    for outcome in outcomes:
        expected = getattr(outcome.case, f"needs_{attr}")
        actual = getattr(outcome, attr)
        if expected and actual:
            tp += 1
        elif expected and not actual:
            fn += 1
        elif not expected and actual:
            fp += 1
    recall = tp / (tp + fn) if (tp + fn) else 1.0
    precision = tp / (tp + fp) if (tp + fp) else 1.0
    return recall, precision, fn, fp


def run(mode: str) -> list[Outcome]:
    print(f"\n=== mode: {mode} ===")
    outcomes: list[Outcome] = []
    for case in CASES:
        outcome = decide(case, mode)
        outcomes.append(outcome)

        want = (
            ("S" if case.needs_security else "-")
            + ("P" if case.needs_performance else "-")
        )
        got = ("S" if outcome.security else "-") + ("P" if outcome.performance else "-")

        # A security false negative is the only failure worth shouting about.
        if case.needs_security and not outcome.security:
            flag = "MISS-SECURITY"
        elif want == got:
            flag = "ok"
        else:
            flag = "differs"

        suffix = " [backstop]" if outcome.forced else ""
        if outcome.error:
            flag, suffix = "ERROR", f" {outcome.error[:60]}"
        print(f"  {case.id:<28} want={want} got={got}  {flag}{suffix}")

    return outcomes


def report(mode: str, outcomes: list[Outcome]) -> float:
    errors = [o for o in outcomes if o.error]
    if errors:
        print(f"\n  {len(errors)} case(s) errored - results below are not meaningful.")

    sec_recall, sec_precision, sec_fn, sec_fp = _scores(outcomes, "security")
    perf_recall, perf_precision, perf_fn, perf_fp = _scores(outcomes, "performance")

    print(f"\n  security     recall {sec_recall:.0%}  precision {sec_precision:.0%}"
          f"   (false negatives: {sec_fn}, false positives: {sec_fp})")
    print(f"  performance  recall {perf_recall:.0%}  precision {perf_precision:.0%}"
          f"   (false negatives: {perf_fn}, false positives: {perf_fp})")

    missed = [o.case.id for o in outcomes if o.case.needs_security and not o.security]
    if missed:
        print(f"  MISSED SECURITY AUDITS: {', '.join(missed)}")
    return sec_recall


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=(*MODES, "both"), default="both")
    parser.add_argument(
        "--min-security-recall",
        type=float,
        default=1.0,
        help="fail (exit 1) if as-shipped security recall is below this (default 1.0)",
    )
    args = parser.parse_args()

    modes = MODES if args.mode == "both" else (args.mode,)
    shipped_recall = None

    print(f"Routing eval - {len(CASES)} labelled cases")
    for mode in modes:
        outcomes = run(mode)
        recall = report(mode, outcomes)
        if mode == "as-shipped":
            shipped_recall = recall

    if shipped_recall is None:
        return 0

    if shipped_recall < args.min_security_recall:
        print(
            f"\nFAIL: as-shipped security recall {shipped_recall:.0%} is below "
            f"the {args.min_security_recall:.0%} threshold."
        )
        return 1

    print(f"\nPASS: as-shipped security recall {shipped_recall:.0%}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
