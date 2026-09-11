"""GitHub tooling layer for the PR bot.

The folder is named ``mcp_clients`` because the spec said so, but **this is
PyGithub, not an MCP server**. MCP's value is letting a *model* discover and call
tools at runtime; these calls are fixed and webhook-driven, so the server would
be a second container wrapping REST calls this backend already makes.

The model-driven tool calling in this project lives in ``agents/supervisor.py``.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger("code_guardian.github")

# Extension -> language name handed to the agents. Anything not listed is not
# reviewed: an agent prompt that says "audit this code" is meaningless against a
# lockfile, a minified bundle or a PNG, and reviewing them burns tokens.
LANGUAGE_BY_EXTENSION: dict[str, str] = {
    ".py": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".mjs": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".java": "java",
    ".go": "go",
    ".rb": "ruby",
    ".php": "php",
    ".cs": "csharp",
    ".rs": "rust",
    ".kt": "kotlin",
    ".sql": "sql",
    ".sh": "bash",
}

# Paths that match any of these are skipped even when the extension is known.
_SKIP_MARKERS = (
    "/node_modules/",
    "/vendor/",
    "/dist/",
    "/build/",
    "/migrations/",
    ".min.js",
    ".lock",
    "-lock.json",
)


@dataclass(frozen=True)
class PullRequestRef:
    """The bits of a webhook payload the bot actually needs."""

    repo_full_name: str
    number: int
    action: str
    head_sha: str = ""
    title: str = ""


@dataclass
class ChangedFile:
    filename: str
    language: str
    patch: str
    additions: int = 0
    status: str = "modified"


@dataclass
class PostResult:
    posted: bool
    reason: str = ""
    comment_url: str = ""
    check_run_url: str = ""
    reviewed_files: list[str] = field(default_factory=list)


# --------------------------------------------------------------------------- #
# Payload parsing - pure functions, no network, so they are cheap to test
# --------------------------------------------------------------------------- #

# Reviews run on open and on every push to the branch. "reopened" is included
# because a PR reopened after changes has never been reviewed by this bot.
REVIEWABLE_ACTIONS = frozenset({"opened", "synchronize", "reopened", "ready_for_review"})


def parse_pull_request_event(payload: dict[str, Any]) -> PullRequestRef | None:
    """Extract a :class:`PullRequestRef`, or None if this event is not one.

    Returning None is the normal case: GitHub sends a lot of events, and the bot
    must ignore everything that is not an actionable pull request update rather
    than erroring on it.
    """
    pull_request = payload.get("pull_request")
    repository = payload.get("repository")
    if not isinstance(pull_request, dict) or not isinstance(repository, dict):
        return None

    action = str(payload.get("action", ""))
    if action not in REVIEWABLE_ACTIONS:
        return None

    if pull_request.get("draft") and action != "ready_for_review":
        return None  # draft PRs are still being written; do not nag

    full_name = repository.get("full_name")
    number = pull_request.get("number")
    if not full_name or not isinstance(number, int):
        return None

    return PullRequestRef(
        repo_full_name=str(full_name),
        number=number,
        action=action,
        head_sha=str((pull_request.get("head") or {}).get("sha", "")),
        title=str(pull_request.get("title", "")),
    )


_PR_URL = re.compile(
    r"(?:https?://)?(?:www\.)?github\.com/"
    r"(?P<owner>[A-Za-z0-9_.-]+)/(?P<repo>[A-Za-z0-9_.-]+)"
    r"/pull/(?P<number>\d+)"
)


def parse_pull_request_url(url: str) -> PullRequestRef | None:
    """Turn a pasted PR link into a reference.

    Also accepts the bare ``owner/repo#123`` shorthand, because that is what
    people type when they are reading a PR rather than looking at its URL.
    """
    text = (url or "").strip()
    match = _PR_URL.search(text)
    if match:
        return PullRequestRef(
            repo_full_name=f"{match.group('owner')}/{match.group('repo')}",
            number=int(match.group("number")),
            action="manual",
        )

    short = re.fullmatch(r"([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)#(\d+)", text)
    if short:
        return PullRequestRef(
            repo_full_name=short.group(1), number=int(short.group(2)), action="manual"
        )
    return None


def language_for_path(path: str) -> str | None:
    """Return the agent-facing language for a path, or None to skip it."""
    # GitHub reports repo-relative paths, so a top-level vendored directory
    # arrives as "node_modules/x.js" with no leading slash. Normalising with a
    # leading "/" lets one marker match both root and nested occurrences without
    # a substring rule loose enough to also match "my_node_modules_helper.js".
    lowered = "/" + path.lower().lstrip("/")
    if any(marker in lowered for marker in _SKIP_MARKERS):
        return None
    for extension, language in LANGUAGE_BY_EXTENSION.items():
        if lowered.endswith(extension):
            return language
    return None


def added_lines(patch: str) -> str:
    """Reduce a unified diff hunk to just the lines this PR introduces.

    The auditors are given added lines rather than the whole patch because a
    reviewer's job on a PR is the new code: flagging a pre-existing issue in an
    untouched context line is noise the author cannot act on in this PR.
    """
    out = []
    for line in (patch or "").splitlines():
        if line.startswith("+") and not line.startswith("+++"):
            out.append(line[1:])
    return "\n".join(out)


# --------------------------------------------------------------------------- #
# Network layer
# --------------------------------------------------------------------------- #

class GitHubClient:
    """Thin PyGithub wrapper. Constructed per request so the token is never
    cached across a config change."""

    def __init__(self, token: str) -> None:
        if not token:
            raise RuntimeError(
                "GITHUB_TOKEN is not set; the PR bot cannot read or comment on "
                "pull requests."
            )
        from github import Auth, Github  # imported lazily: Phase 1 does not need it

        self._client = Github(auth=Auth.Token(token))

    def changed_files(self, repo_full_name: str, number: int, limit: int = 10) -> list[ChangedFile]:
        """Return the reviewable files in a PR, newest-largest first.

        ``limit`` exists because a 200-file PR would otherwise fire 400 LLM
        calls. Files are ranked by additions so that when the cap bites, the bot
        reviews the substantial changes rather than whichever files GitHub
        happened to list first.
        """
        pull = self._client.get_repo(repo_full_name).get_pull(number)

        candidates: list[ChangedFile] = []
        for file in pull.get_files():
            if file.status == "removed" or not file.patch:
                continue
            language = language_for_path(file.filename)
            if language is None:
                continue
            candidates.append(
                ChangedFile(
                    filename=file.filename,
                    language=language,
                    patch=file.patch,
                    additions=file.additions,
                    status=file.status,
                )
            )

        candidates.sort(key=lambda f: f.additions, reverse=True)
        return candidates[:limit]

    def create_check_run(
        self,
        repo_full_name: str,
        head_sha: str,
        conclusion: str,
        title: str,
        summary: str,
    ) -> str:
        """Publish a Check Run against the PR's head commit.

        This is what turns "posts a comment" into "can gate a merge": with the
        check marked required in branch protection, a ``failure`` conclusion
        blocks the merge button.

        GitHub caps the output text at 65535 characters.
        """
        repo = self._client.get_repo(repo_full_name)
        check = repo.create_check_run(
            name="Code Guardian",
            head_sha=head_sha,
            status="completed",
            conclusion=conclusion,
            output={"title": title[:255], "summary": summary[:65000]},
        )
        return check.html_url

    def post_comment(self, repo_full_name: str, number: int, body: str) -> str:
        """Post the review as an issue comment on the PR; returns its URL."""
        pull = self._client.get_repo(repo_full_name).get_pull(number)
        comment = pull.create_issue_comment(body)
        return comment.html_url
