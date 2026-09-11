"""Phase 2: the GitHub pull-request bot.

Flow: webhook -> signature check -> event filter -> (background) review each
changed file -> one aggregated comment on the PR.

The review itself is the same graph Phase 1 uses. Nothing about the agents
changes for a PR; only the input source and the output sink do.
"""

from __future__ import annotations

import hashlib
import hmac
import logging

from .config import get_settings
from .graph import run_review
from .mcp_clients.github_client import (
    ChangedFile,
    GitHubClient,
    PostResult,
    PullRequestRef,
    added_lines,
)

logger = logging.getLogger("code_guardian.pr_bot")

# A PR touching auth or database code is exactly the high-stakes path §3a
# describes, but the bot cannot know that per-file in advance, so it relies on
# the supervisor's own backstop rather than forcing a full audit on everything.
MAX_FILES = 10


def verify_signature(secret: str, body: bytes, signature_header: str | None) -> tuple[bool, str]:
    """Validate GitHub's ``X-Hub-Signature-256`` header.

    Returns ``(ok, reason)``. This **fails closed**: if no secret is configured
    the request is rejected rather than trusted. An unauthenticated webhook
    endpoint that runs LLM calls and writes comments to your repositories is a
    denial-of-wallet and a spam vector, and "I forgot to set the secret" must
    not silently become "anyone on the internet can drive this bot".
    """
    if not secret:
        return False, (
            "GITHUB_WEBHOOK_SECRET is not configured; refusing to process "
            "unauthenticated webhook deliveries."
        )
    if not signature_header:
        return False, "missing X-Hub-Signature-256 header"

    algorithm, _, sent = signature_header.partition("=")
    if algorithm != "sha256" or not sent:
        return False, "malformed X-Hub-Signature-256 header"

    expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    # compare_digest, not ==: a plain comparison leaks the correct prefix length
    # through timing and turns the secret into a guessable one byte at a time.
    if not hmac.compare_digest(expected, sent):
        return False, "signature mismatch"
    return True, ""


def _render_pr_comment(ref: PullRequestRef, results: list[tuple[ChangedFile, dict]]) -> str:
    """Aggregate per-file reviews into one PR comment."""
    total_security = sum(len(r.get("security_issues") or []) for _, r in results)
    total_performance = sum(len(r.get("performance_issues") or []) for _, r in results)
    failed = [
        (f.filename, r.get("failed_audits") or [])
        for f, r in results
        if r.get("failed_audits")
    ]

    lines = ["## Code Guardian review", ""]

    if failed:
        lines += [
            "> **This review is incomplete.** One or more audits failed to run, "
            "so the results below are not a clean bill of health:",
            "",
        ]
        for filename, audits in failed:
            lines.append(f"> - `{filename}`: {', '.join(audits)}")
        lines.append("")

    # The PR-level score is the worst file's, not an average: a PR is exactly as
    # risky as its most dangerous change, and averaging would let one clean file
    # dilute a Critical finding in another.
    scored = [r.get("risk") or {} for _, r in results]
    complete = [r for r in scored if r.get("complete", True) and r.get("score") is not None]
    worst = max(complete, key=lambda r: r.get("score", 0), default=None)

    if worst is not None and len(complete) == len(scored):
        lines += [
            f"**Risk {worst.get('score', 0)}/100 — {str(worst.get('band', 'none')).upper()}** "
            f"(highest-risk file). {worst.get('note', '')}",
            "",
        ]
    elif scored:
        lines += [
            "**Risk score unavailable** — at least one audit did not run.",
            "",
        ]

    lines += [
        f"Reviewed **{len(results)} file(s)** · "
        f"**{total_security} security** / **{total_performance} performance** finding(s).",
        "",
    ]

    if not total_security and not total_performance and not failed:
        lines += ["No issues found in the added lines of this PR.", ""]

    for changed, result in results:
        security = result.get("security_issues") or []
        performance = result.get("performance_issues") or []
        routed = result.get("routed_to") or []
        file_failed = result.get("failed_audits") or []

        if not security and not performance and not file_failed:
            continue

        lines += [f"### `{changed.filename}`", ""]
        if file_failed:
            lines += [
                f"**Audit failed ({', '.join(file_failed)}) - this file was not fully checked.**",
                "",
            ]
        if routed:
            lines += [
                "_Auditors run: " + ", ".join(r.replace("_", " ") for r in routed) + "._",
                "",
            ]

        for finding in security + performance:
            severity = finding.get("severity", "Medium")
            title = finding.get("title", "Untitled finding")
            lines.append(f"- **[{severity}] {title}**")
            if finding.get("line_hint"):
                lines.append(f"  - `{finding['line_hint']}`")
            if finding.get("explanation"):
                lines.append(f"  - {finding['explanation']}")
            if finding.get("recommendation"):
                lines.append(f"  - _Fix:_ {finding['recommendation']}")
        lines.append("")

        diff = result.get("diff") or ""
        if diff:
            lines += ["<details><summary>Suggested patch</summary>", "", "```diff",
                      diff.rstrip("\n"), "```", "", "</details>", ""]

    lines.append(
        "<sub>Generated by Code Guardian on the lines this PR adds. "
        "Review before merging.</sub>"
    )
    return "\n".join(lines)


def collect_reviews(
    ref: PullRequestRef, client: GitHubClient
) -> list[tuple[ChangedFile, dict]]:
    """Review every reviewable file in a PR, without posting anything.

    Split out from :func:`review_pull_request` so the UI can show a PR review
    without writing a comment to somebody's repository. Reading a PR and
    commenting on it are different levels of consequence, and only the webhook
    path should do the second.
    """
    files = client.changed_files(ref.repo_full_name, ref.number, limit=MAX_FILES)

    results: list[tuple[ChangedFile, dict]] = []
    for changed in files:
        snippet = added_lines(changed.patch)
        if not snippet.strip():
            continue
        try:
            state = run_review(source_code=snippet, language=changed.language)
        except Exception as exc:  # noqa: BLE001
            # One bad file must not sink the whole review; record it as a failed
            # audit so the comment says so rather than omitting the file silently.
            logger.exception("Review failed for %s", changed.filename)
            state = {
                "failed_audits": ["security_audit", "performance_audit"],
                "audit_errors": [f"{changed.filename}: {exc}"],
            }
        results.append((changed, state))
    return results


def render_comment(ref: PullRequestRef, results: list[tuple[ChangedFile, dict]]) -> str:
    """Public wrapper so the API can show the comment it *would* post."""
    return _render_pr_comment(ref, results)


# Bands at or above this block the merge. "high" means one Critical finding is
# enough, which is the calibration risk.py was built around.
BLOCKING_BANDS = frozenset({"high", "critical"})


def check_run_verdict(results: list[tuple[ChangedFile, dict]]) -> tuple[str, str, str]:
    """Decide the Check Run conclusion from the worst file's risk.

    Returns ``(conclusion, title, summary)``.

    ``action_required`` rather than ``success`` or ``failure`` when any audit did
    not run. Passing would be dangerous - nothing actually examined that file -
    and failing would be wrong, because nothing is known either way. "A human
    should look" is the only honest verdict.
    """
    scored = [r.get("risk") or {} for _, r in results]
    incomplete = [r for r in scored if not r.get("complete", True)]

    if incomplete:
        return (
            "action_required",
            "Review incomplete - a human should look",
            "One or more audits did not run, so this PR was not fully checked. "
            "The risk score is unavailable rather than low.",
        )

    worst = max(scored, key=lambda r: r.get("score", 0), default={})
    score = worst.get("score", 0)
    band = str(worst.get("band", "none"))
    findings = sum(
        len(r.get("security_issues") or []) + len(r.get("performance_issues") or [])
        for _, r in results
    )

    summary = (
        f"{findings} finding(s) across {len(results)} file(s). "
        f"Highest-risk file scores {score}/100 ({band}). "
        "The score is the worst file's, not an average - a PR is as risky as its "
        "most dangerous change."
    )

    if band in BLOCKING_BANDS:
        return "failure", f"Risk {score}/100 - {band}", summary
    return "success", f"Risk {score}/100 - {band}", summary


def publish_check_run(
    ref: PullRequestRef, client: GitHubClient, results: list[tuple[ChangedFile, dict]]
) -> str:
    """Publish the verdict. Returns the check URL, or "" if it could not be sent."""
    if not ref.head_sha:
        # Manual runs (a pasted PR link) carry no head SHA; only the webhook does.
        return ""

    conclusion, title, summary = check_run_verdict(results)
    try:
        url = client.create_check_run(
            ref.repo_full_name, ref.head_sha, conclusion, title, summary
        )
    except Exception as exc:  # noqa: BLE001
        # A missing checks:write permission must not lose the review comment.
        logger.warning("Could not publish Check Run: %s", exc)
        return ""

    logger.info("Check Run %s for %s#%s", conclusion, ref.repo_full_name, ref.number)
    return url


def review_pull_request(ref: PullRequestRef) -> PostResult:
    """Review a PR and post the result. Runs in a background task."""
    settings = get_settings()
    try:
        client = GitHubClient(settings.github_token)
    except RuntimeError as exc:
        logger.error("PR bot misconfigured: %s", exc)
        return PostResult(posted=False, reason=str(exc))

    try:
        results = collect_reviews(ref, client)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Could not read PR files")
        return PostResult(posted=False, reason=f"could not read PR files: {exc}")

    if not results:
        return PostResult(posted=False, reason="no reviewable added lines in this PR")

    body = _render_pr_comment(ref, results)
    try:
        url = client.post_comment(ref.repo_full_name, ref.number, body)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Could not post PR comment")
        return PostResult(posted=False, reason=f"could not post comment: {exc}")

    # Published after the comment, so a checks:write failure cannot cost the
    # review itself.
    check_url = publish_check_run(ref, client, results)

    logger.info("PR %s#%s reviewed: %s", ref.repo_full_name, ref.number, url)
    return PostResult(
        posted=True,
        comment_url=url,
        check_run_url=check_url,
        reviewed_files=[f.filename for f, _ in results],
    )
