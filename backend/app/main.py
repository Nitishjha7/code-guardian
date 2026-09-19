"""FastAPI entry point.

Exposes the review graph over HTTP. This is the module the deploy guide's start
command points at: ``uvicorn app.main:app``.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from pathlib import Path
from typing import Any, Literal

import anyio
from fastapi import BackgroundTasks, FastAPI, Header, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from pydantic import BaseModel, Field, field_validator

from . import __version__, pr_bot
from .config import get_settings
from .graph import run_review, run_review_stream
from .guardrails_config import validators
from .logging_config import configure_json_logging
from .mcp_clients import github_client
from .memory import long_term as memory_long_term
from .memory.semantic import consolidate_facts

configure_json_logging()
logger = logging.getLogger("code_guardian")

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
    repo_id: str = Field(
        default="",
        max_length=200,
        description=(
            "Optional 'owner/repo'. Applies that repository's stored preferences "
            "(PUT /api/preferences/{repo_id}) and attributes the recorded episode "
            "to it. Empty means an ad-hoc review with no repository context."
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
    memory_note: str = ""

    @field_validator(
        "title", "line_hint", "explanation", "recommendation", "source",
        "complexity_before", "complexity_after", "memory_note",
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
    token_usage: dict[str, Any] = {}


def _review_response(state: dict[str, Any], fallback_language: str) -> ReviewResponse:
    """Build the response payload from graph state.

    One function so ``/api/review`` and the streaming endpoint's final event
    build the same payload; keeping two field lists in sync is how the two
    responses drift apart.
    """
    return ReviewResponse(
        language=state.get("language", fallback_language),
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
        token_usage=state.get("token_usage", {}),
    )


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
        "fallback_models": settings.fallback_model_list,
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
                repo_id=request.repo_id,
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

    return _review_response(state, request.language)


@app.post("/api/review/stream")
async def review_stream(request: ReviewRequest) -> StreamingResponse:
    """Same review as ``/api/review``, as Server-Sent Events.

    A vulnerable-Python sample takes over ten seconds end to end and a plain
    CSS file well under one - ``/api/review`` makes both look identical to the
    caller until the whole thing finishes. This streams a ``progress`` event
    the moment each graph node completes (which auditor started, which
    finished, when the patch generator kicked in) and a final ``done`` event
    carrying the exact payload ``/api/review`` would have returned in one
    shot - see ``_review_response``, used by both.

    ``run_review_stream`` is a plain generator wrapping ``graph.stream(...)``;
    the queue and the background thread below exist only to get a synchronous
    generator's output onto the async event loop without blocking it, the same
    problem ``anyio.to_thread.run_sync`` solves for the non-streaming endpoint.
    """
    queue: asyncio.Queue = asyncio.Queue()
    # get_running_loop, not get_event_loop: the producer thread posts onto this
    # loop from off-thread, so it has to be the one actually serving the request.
    loop = asyncio.get_running_loop()
    SENTINEL = object()

    def produce() -> None:
        try:
            for kind, payload in run_review_stream(
                source_code=request.source_code,
                language=request.language,
                force_full_audit=request.force_full_audit,
                repo_id=request.repo_id,
            ):
                if kind == "done":
                    payload = _review_response(payload, request.language).model_dump()
                asyncio.run_coroutine_threadsafe(
                    queue.put((kind, payload)), loop
                ).result()
        except Exception as exc:  # noqa: BLE001 - reported to the client as an event, not a 500
            logger.exception("Streaming review failed")
            asyncio.run_coroutine_threadsafe(
                queue.put(("error", {"detail": str(exc)})), loop
            ).result()
        finally:
            asyncio.run_coroutine_threadsafe(queue.put((SENTINEL, None)), loop).result()

    async def event_source():
        # The producer runs as a task rather than being awaited here: awaiting it
        # would finish the whole review before the first event was yielded, which
        # is a non-streaming endpoint wearing an SSE content-type. Starting it
        # concurrently and draining as it goes is the entire point of the queue.
        worker = asyncio.create_task(
            anyio.to_thread.run_sync(produce, limiter=_REVIEW_LIMITER)
        )
        try:
            while True:
                kind, payload = await queue.get()
                if kind is SENTINEL:
                    return
                yield f"event: {kind}\ndata: {json.dumps(payload)}\n\n"
        finally:
            # On a client disconnect the generator is closed mid-drain. The
            # worker thread cannot be cancelled (it is blocked in sync LLM
            # calls), but awaiting it here keeps the limiter slot accounted for
            # instead of leaking it, and surfaces any error it raised.
            with contextlib.suppress(Exception):
                await worker

    return StreamingResponse(event_source(), media_type="text/event-stream")


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


class PreferenceRequest(BaseModel):
    key: str = Field(..., max_length=100)
    value: str = Field(..., max_length=500)


class PreferencesResponse(BaseModel):
    repo_id: str
    preferences: dict[str, str] = {}


@app.put("/api/preferences/{repo_id:path}", response_model=PreferencesResponse)
def set_preference(repo_id: str, request: PreferenceRequest) -> PreferencesResponse:
    """Set one explicit review preference for a repo (e.g. ``owner/repo``).

    ``repo_id`` is ``PullRequestRef.repo_full_name`` - the same key
    ``/api/review-pr`` and the webhook already use to identify a repository,
    not a new identity invented for this endpoint. See app/memory/long_term.py
    for why preferences are scoped this way and never inferred.
    """
    memory_long_term.set_preference(repo_id, request.key, request.value)
    return PreferencesResponse(repo_id=repo_id, preferences=memory_long_term.get_preferences(repo_id))


@app.get("/api/preferences/{repo_id:path}", response_model=PreferencesResponse)
def get_preferences(repo_id: str) -> PreferencesResponse:
    return PreferencesResponse(repo_id=repo_id, preferences=memory_long_term.get_preferences(repo_id))


@app.post("/api/memory/consolidate")
def trigger_consolidation() -> dict[str, int]:
    """Manually run semantic-fact consolidation over recorded episodes.

    Deliberately not on a schedule inside this process - see the module
    docstring in app/memory/semantic.py for why this is a periodic, explicit
    job rather than something that runs on every review.
    """
    return {"facts_written": consolidate_facts()}


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


@app.get("/metrics")
def metrics() -> Response:
    """Prometheus scrape target — reviews, findings, audit failures, and the
    LLM gateway's own call/token/fallback counts. See app/metrics.py for why
    each metric exists; none of them are generic request counters."""
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


# Mounted last: a mount at "/" swallows every path beneath it, so the API routes
# above must be registered first. Only the single-service deploy image has this
# directory — under compose, nginx serves the frontend and this is a no-op.
#
# The SPA routes on the URL hash, so `html=True` is all the fallback needed.
STATIC_DIR = Path(__file__).resolve().parent.parent / "static"


class _CachingStatics(StaticFiles):
    """StaticFiles, but with cache headers Vite's output actually needs.

    Everything under /assets/ carries a content hash in its filename, so it can
    be cached indefinitely. index.html cannot: its URL is the same on every
    deploy, and a cached copy keeps referencing the previous build's hashed
    bundles, so the browser loads the old UI and no amount of redeploying fixes
    it. StaticFiles sends neither header by default.
    """

    def file_response(self, full_path, stat_result, scope, status_code=200):
        response = super().file_response(full_path, stat_result, scope, status_code)
        path = str(full_path).replace("\\", "/")
        if "/assets/" in path:
            response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        else:
            response.headers["Cache-Control"] = "no-cache, must-revalidate"
        return response


if STATIC_DIR.is_dir():
    app.mount("/", _CachingStatics(directory=STATIC_DIR, html=True), name="static")
    logger.info("Serving the built frontend from %s", STATIC_DIR)
