"""FastAPI entry point.

Exposes the review graph over HTTP. This is the module the deploy guide's start
command points at: ``uvicorn app.main:app``.
"""

from __future__ import annotations

import logging
from typing import Any, Literal

import anyio
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, field_validator

from . import __version__
from .config import get_settings
from .graph import run_review
from .guardrails_config import validators

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
    complexity_before: str = "n/a"
    complexity_after: str = "n/a"

    @field_validator(
        "title", "line_hint", "explanation", "recommendation",
        "complexity_before", "complexity_after",
        mode="before",
    )
    @classmethod
    def _stringify(cls, value: Any) -> str:
        return "" if value is None else str(value)


class ReviewResponse(BaseModel):
    language: str
    routed_to: list[str]
    failed_audits: list[str]
    audit_errors: list[str]
    security_issues: list[Finding]
    performance_issues: list[Finding]
    fixed_code: str
    diff: str
    summary_report: str
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
        failed_audits=state.get("failed_audits", []),
        audit_errors=state.get("audit_errors", []),
        security_issues=[Finding(**f) for f in state.get("security_issues", [])],
        performance_issues=[Finding(**f) for f in state.get("performance_issues", [])],
        fixed_code=state.get("fixed_code", ""),
        diff=state.get("diff", ""),
        summary_report=state.get("summary_report", ""),
        guardrail_report=state.get("guardrail_report", {}),
        logs=state.get("logs", []),
    )


@app.get("/api/graph")
def graph_topology() -> dict[str, Any]:
    """Return the compiled graph as Mermaid, for the UI's architecture panel."""
    from .graph import get_graph

    try:
        mermaid = get_graph().get_graph().draw_mermaid()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {"mermaid": mermaid}
