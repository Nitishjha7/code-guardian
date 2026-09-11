"""FastAPI entry point.

Exposes the review graph over HTTP. This is the module the deploy guide's start
command points at: ``uvicorn app.main:app``.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Literal

import anyio
from fastapi import BackgroundTasks, FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator

from . import __version__, pr_bot
from .config import get_settings
from .graph import run_review
from .guardrails_config import validators
from .mcp_clients import github_client

logger = logging.getLogger("code_guardian")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

app = FastAPI(
    title="Code Guardian",
    description="Multi-agent autonomous code reviewer and PR bot.",
    version=__version__,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

# The graph is synchronous (LangChain's sync client) so it must not run on the
# event loop. The limiter also caps how many concurrent reviews can be in flight
# against the Groq rate limit.
_REVIEW_LIMITER = anyio.CapacityLimiter(4)


# --------------------------------------------------------------------------- #
# Schemas
# --------------------------------------------------------------------------- #

class ReviewRequest(BaseModel):
    source_code: str = Field(..., min_length=1, max_length=200_000)
    language: str = Field(default="python", max_length=40)
    force_full_audit: bool = Field(
        default=False,
        description=(
            "Bypass the supervisor's routing and run every auditor. Use for "
            "high-stakes paths where a false negative is unacceptable."
        ),
    )


class Finding(BaseModel):
    """One agent finding.

    Fields are coerced to strings before validation: the findings come from an
    LLM, and a model that returns ``"line_hint": 42`` should not fail the whole
    request.
    """

    title: str = "Untitled finding"
    severity: Literal["Critical", "High", "Medium", "Low"] = "Medium"
    line_hint: str = ""
    explanation: str = ""
    recommendation: str = ""
    source: str = "llm"
    complexity_before: str = "n/a"
    complexity_after: str = "n/a"

    @field_validator(
        "title", "line_hint", "explanation", "recommendation", "source",
        "complexity_before", "complexity_after",
        mode="before",
    )
    @classmethod
    def _stringify(cls, value: Any) -> str:
        return "" if value is None else str(value)


class RiskScore(BaseModel):
    score: int = 0
    band: str = "none"
    complete: bool = True
    size_modifier: float = 1.0
    drivers: list[str] = []
    note: str = ""


class ReviewResponse(BaseModel):
    language: str
    routed_to: list[str]
    risk: RiskScore = RiskScore()
    failed_audits: list[str]
    audit_errors: list[str]
    security_issues: list[Finding]
    performance_issues: list[Finding]
    fixed_code: str
    diff: str
    summary_report: str
    generated_tests: str = ""
    tests_note: str = ""
    guardrail_report: dict[str, Any]
    logs: list[str]


# --------------------------------------------------------------------------- #
# Routes
# --------------------------------------------------------------------------- #

@app.get("/api/health")
def health() -> dict[str, Any]:
    settings = get_settings()
    return {
        "status": "ok",
        "version": __version__,
        "model": settings.guardian_model,
        "groq_key_configured": bool(settings.groq_api_key),
        "guardrails": validators.describe(),
        "pr_bot": {
            # Both must be true for the webhook to do anything: without the
            # secret it refuses deliveries, without the token it cannot comment.
            "github_token_configured": bool(settings.github_token),
            "webhook_secret_configured": bool(settings.github_webhook_secret),
        },
    }


@app.post("/api/review", response_model=ReviewResponse)
async def review(request: ReviewRequest) -> ReviewResponse:
    """Run the full multi-agent review over a code submission."""
    try:
        state = await anyio.to_thread.run_sync(
            lambda: run_review(
                source_code=request.source_code,
                language=request.language,
                force_full_audit=request.force_full_audit,
            ),
            limiter=_REVIEW_LIMITER,
        )
    except RuntimeError as exc:  # missing API key, surfaced from config.get_llm
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001 - the boundary has to be broad
        logger.exception("Review failed")
        # A rejected key or an exhausted quota is a configuration problem, not a
        # bug in the review. Say so, rather than showing the operator a 500 and
        # a raw provider payload.
        text = str(exc).lower()
        if "invalid api key" in text or "401" in text or "authentication" in text:
            raise HTTPException(
                status_code=502,
                detail="The LLM provider rejected the API key. Check GROQ_API_KEY.",
            ) from exc
        if "rate limit" in text or "429" in text or "quota" in text:
            raise HTTPException(
                status_code=429,
                detail="The LLM provider is rate limiting this key. Retry shortly.",
            ) from exc
        raise HTTPException(status_code=500, detail=f"Review failed: {exc}") from exc

    return ReviewResponse(
        language=state.get("language", request.language),
        routed_to=state.get("routed_to", []),
        risk=RiskScore(**(state.get("risk") or {})),
        failed_audits=state.get("failed_audits", []),
        audit_errors=state.get("audit_errors", []),
        security_issues=[Finding(**f) for f in state.get("security_issues", [])],
        performance_issues=[Finding(**f) for f in state.get("performance_issues", [])],
        fixed_code=state.get("fixed_code", ""),
        diff=state.get("diff", ""),
        summary_report=state.get("summary_report", ""),
        generated_tests=state.get("generated_tests", ""),
        tests_note=state.get("tests_note", ""),
        guardrail_report=state.get("guardrail_report", {}),
        logs=state.get("logs", []),
    )


class ReviewPRRequest(BaseModel):
    url: str = Field(..., max_length=500, description="PR link or owner/repo#123")


class PRFileReview(BaseModel):
    filename: str
    language: str
    additions: int = 0
    risk: RiskScore = RiskScore()
    security_issues: list[Finding] = []
    performance_issues: list[Finding] = []
    failed_audits: list[str] = []
    diff: str = ""


class ReviewPRResponse(BaseModel):
    repository: str
    number: int
    files: list[PRFileReview]
    comment_markdown: str
    posted: bool = False


@app.post("/api/review-pr", response_model=ReviewPRResponse)
async def review_pr(request: ReviewPRRequest) -> ReviewPRResponse:
    """Review a pull request on demand, **without posting anything**.

    Reading a PR and commenting on it are different levels of consequence. This
    endpoint only reads: the comment it would post is returned for preview, and
    only the webhook path actually writes to a repository.
    """
    ref = github_client.parse_pull_request_url(request.url)
    if ref is None:
        raise HTTPException(
            status_code=400,
            detail="Could not read that as a pull request. Use a github.com PR link "
            "or the owner/repo#123 shorthand.",
        )

    settings = get_settings()
    if not settings.github_token:
        raise HTTPException(
            status_code=503,
            detail="GITHUB_TOKEN is not set, so pull requests cannot be read. "
            "Add it to backend/.env and restart.",
        )

    def _run() -> tuple[list, str]:
        client = github_client.GitHubClient(settings.github_token)
        results = pr_bot.collect_reviews(ref, client)
        return results, pr_bot.render_comment(ref, results) if results else ""

    try:
        results, comment = await anyio.to_thread.run_sync(_run, limiter=_REVIEW_LIMITER)
    except Exception as exc:  # noqa: BLE001
        logger.exception("PR review failed")
        text = str(exc).lower()
        if "404" in text or "not found" in text:
            raise HTTPException(
                status_code=404,
                detail=f"{ref.repo_full_name}#{ref.number} not found, or the token "
                "cannot see it.",
            ) from exc
        if "403" in text or "rate limit" in text:
            raise HTTPException(
                status_code=429, detail="GitHub is rate limiting this token."
            ) from exc
        raise HTTPException(status_code=502, detail=f"PR review failed: {exc}") from exc

    if not results:
        raise HTTPException(
            status_code=422,
            detail="No reviewable added lines in this PR (only generated, vendored "
            "or non-source files changed).",
        )

    return ReviewPRResponse(
        repository=ref.repo_full_name,
        number=ref.number,
        comment_markdown=comment,
        files=[
            PRFileReview(
                filename=changed.filename,
                language=changed.language,
                additions=changed.additions,
                risk=RiskScore(**(state.get("risk") or {})),
                security_issues=[
                    Finding(**f) for f in state.get("security_issues", [])
                ],
                performance_issues=[
                    Finding(**f) for f in state.get("performance_issues", [])
                ],
                failed_audits=state.get("failed_audits", []),
                diff=state.get("diff", ""),
            )
            for changed, state in results
        ],
    )


@app.post("/webhook/github", status_code=202)
async def github_webhook(
    request: Request,
    background: BackgroundTasks,
    x_hub_signature_256: str | None = Header(default=None),
    x_github_event: str | None = Header(default=None),
) -> dict[str, Any]:
    """GitHub pull-request webhook (Phase 2).

    Returns 202 immediately and reviews in the background: a full review takes
    several seconds per file, and GitHub abandons a webhook delivery after 10.
    Doing the work inline would make every non-trivial PR look like a failed
    delivery in the repository's webhook log.
    """
    body = await request.body()
    settings = get_settings()

    ok, reason = pr_bot.verify_signature(
        settings.github_webhook_secret, body, x_hub_signature_256
    )
    if not ok:
        logger.warning("Rejected webhook delivery: %s", reason)
        # 401 for a bad or missing signature; 503 when the server itself has no
        # secret configured, since that is our misconfiguration, not the sender's.
        status = 503 if "not configured" in reason else 401
        raise HTTPException(status_code=status, detail=reason)

    if x_github_event == "ping":
        return {"status": "pong"}
    if x_github_event != "pull_request":
        return {"status": "ignored", "reason": f"event '{x_github_event}' is not handled"}

    try:
        payload = json.loads(body)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="body is not valid JSON") from exc

    ref = github_client.parse_pull_request_event(payload)
    if ref is None:
        return {"status": "ignored", "reason": "not an actionable pull request update"}

    background.add_task(pr_bot.review_pull_request, ref)
    logger.info("Queued review for %s#%s (%s)", ref.repo_full_name, ref.number, ref.action)
    return {
        "status": "queued",
        "repository": ref.repo_full_name,
        "pull_request": ref.number,
        "action": ref.action,
    }


@app.get("/api/graph")
def graph_topology() -> dict[str, Any]:
    """Return the compiled graph as Mermaid, for the UI's architecture panel."""
    from .graph import get_graph

    try:
        mermaid = get_graph().get_graph().draw_mermaid()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {"mermaid": mermaid}


# Mounted last, and deliberately so: a mount at "/" swallows every path beneath
# it, so every API route above has to be registered first or it becomes
# unreachable.
#
# Only the single-service deploy image has this directory. Under docker-compose
# nginx serves the frontend and this block is a no-op, which is why the check is
# on the directory rather than on an env var — one fewer thing to set correctly.
#
# The SPA keeps its page in the URL *hash* (`lib/router.js`), so every route is
# the same document and `html=True` is all the fallback this needs. A path-based
# router would need a catch-all returning index.html.
STATIC_DIR = Path(__file__).resolve().parent.parent / "static"
if STATIC_DIR.is_dir():
    app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
    logger.info("Serving the built frontend from %s", STATIC_DIR)
