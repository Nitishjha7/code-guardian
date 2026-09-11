# Build & Deploy Guide

What to prioritise when building this as an interview showcase, and how to
deploy it. The interview *answers* live in [INTERVIEW_NOTES.md](INTERVIEW_NOTES.md);
this doc is about build order and deployment.

## Purpose

The goal is to **show the project in an interview**, so depth and explainability
matter more than breadth. Phases 3–5 do not need building — having them written
down as a considered roadmap does the job.

## What to build, in priority order

### 1. Core — build these, well

- **LangGraph multi-agent graph** — Security, Performance and Patch Generator
  wired through `StateGraph`. The most important part.
- **Tool-calling supervisor** — do not make it a fixed fan-out. Expose the
  specialists as `@tool`, bind with `llm.bind_tools([...])`, loop via `ToolNode`
  and a conditional edge. **This is the differentiating piece**: it is the one
  place in the portfolio where the *model* decides control flow (the other two
  projects let LangGraph edges decide). "Have you built ReAct-style tool
  calling?" is a common agentic-AI question, and without this the answer is no.
  Defence in [TECHNICAL_SPEC §3a](TECHNICAL_SPEC.md).
- **FastAPI backend** — `/api/review` accepting code and driving the graph.
- **React UI** — editor, Review button, result cards.
- **Output guardrails** — validate that diffs and comments leak no secrets.
  Shows production thinking.
- **Clean architecture** — a real state schema, separated nodes, and docs.

### 2. Nice-to-have — built

- **GitHub PR Bot (Phase 2)** ✅ — a webhook listener that triggers on PR
  open/update, fetches the diff, and posts a review comment. A strong
  differentiator: real automation rather than a toy demo. Setup in the
  [README](../README.md#github-pr-bot-phase-2).

### 3. Skip — leave in the roadmap

- Phase 3 (Code Quality, Dependency/License, Documentation agents)
- Phase 4 (feedback loop, vector-DB memory, team-specific rules)
- Phase 5 (CI/CD auto-block, chat alerts, auto-ticketing)

These are written up in [ROADMAP.md](ROADMAP.md) with the reason each is
deferred. An interviewer sees that you thought ahead without burning weeks.

## Before you demo: Groq retires model ids

`llama-3.3-70b-versatile` (in the original spec) no longer exists on Groq — it
404s. Check first:

```bash
curl https://api.groq.com/openai/v1/models -H "Authorization: Bearer $GROQ_API_KEY"
```

Put a working id in `GUARDIAN_MODEL`. The default is `openai/gpt-oss-120b`, and
**it must support tool calling** — the supervisor depends on it.

Also watch the daily token quota. The free tier is 200k tokens/day *per model*;
heavy testing the day before a demo will exhaust it. Switching to
`openai/gpt-oss-20b` gets you a separate bucket.

## Build order (status)

1. ✅ `backend/app/graph.py` — `StateGraph` + `ReviewerState` (in `state.py`)
2. ✅ `agents/security_agent.py` + `performance_agent.py` — focused prompts
3. ✅ `agents/patch_generator.py` — synthesize findings into a diff
4. ✅ `guardrails_config/` — secrets + tone guard on all outbound text
5. ✅ FastAPI `/api/review` wiring the graph (`app/main.py`)
6. ✅ React frontend — editor, findings, patch, tests, agent log
7. ✅ GitHub PR bot — `/webhook/github` with HMAC auth, `pr_bot.py`
8. ✅ Bandit fusion, risk score, test generation, held-out routing eval

## How this was built

The code was written with heavy use of an AI coding assistant (Claude), working
through the order above, with each stage run against the real Groq API before
moving on.

What that did **not** decide: that the supervisor should route instead of fanning
out and that the routing claim had to be measured rather than asserted, that a
second eval set had to be held out and never tuned against, that a failed audit
reporting "no issues found" was the worst possible bug for an auditing tool, that
the diff should be computed with `difflib` rather than requested from a model, and
that "MCP" must not be claimed for a folder that runs PyGithub.

Those judgements are the project, and the notes below are where they are defended.

## Implementation notes worth knowing before the interview

Six places where the code deliberately departs from the naive reading of the
spec. Each is a decision to defend, not an accident.

- **A failed audit is never rendered as "no issues found".** Lead with this; it
  was a real bug. The audits are tools, and LangGraph's `ToolNode` turns an
  uncaught exception into a plain ToolMessage — so when the Groq model id was
  retired and every audit 404'd, the system reported **0 findings on code with a
  Critical SQL injection**. For an auditing tool that is the worst possible
  failure: silence became indistinguishable from a pass. Fixed with a
  `{"ok": bool, ...}` envelope per tool, `failed_audits` / `audit_errors` in
  state, and a report that leads with an "incomplete review" banner. Four tests
  pin it down. Good answer to *"how do you know your agent actually worked?"* —
  you don't, unless "did not run" is a distinct state from "ran and found
  nothing".

- **The diff is computed with `difflib`, not asked for from the LLM.** Models
  emit unified diffs with wrong hunk headers and line counts, and such a patch
  will not apply. The model returns the rewritten file; the diff is derived from
  the two texts, exact by construction.

- **Guardrails AI is optional; a local pattern scanner is the default.** Some
  `guardrails-ai` hub validators pull a full torch install — a bad trade for a
  container that otherwise fits in a few hundred MB. The fallback is a real
  guard (11 secret patterns, placeholder-aware so it does not flag the
  `os.environ[...]` a fix is *supposed* to emit), and `guardrail_report.engine`
  always names which engine ran. **Do not claim "Guardrails AI" without saying
  this.**

- **The "MCP client" layer is PyGithub, not an MCP server.** The folder is named
  `mcp_clients/` because the spec said so. Running the MCP server would mean a
  second container wrapping REST calls this backend already makes, and MCP's
  value — a *model* discovering and calling tools at runtime — does not apply to
  fixed, webhook-driven calls. **If you say "MCP", say it about
  `supervisor.py`.** Claiming an integration you did not build is the one thing
  that will sink you here.

- **The router has a static backstop.** `looks_high_stakes()` force-runs both
  auditors when the input obviously touches auth, DB or exec surfaces, so recall
  does not depend on the caller setting `force_full_audit`. Deliberately
  over-inclusive: a false positive costs one audit, a false negative costs a
  vulnerability.

- **Test generation never executes.** Running LLM-authored tests safely needs a
  sandbox; the report says "generated, not executed".

## What is tested

`backend/tests/` covers the LLM-free seams — JSON recovery from messy model
output, diff generation, the routing predicate, the state collector (including
failed and malformed audits), every guardrail pattern, and the whole Phase 2
surface: HMAC verification, event filtering, file selection, PR-link parsing and
added-line extraction.

**107 tests, no API key needed.** Not covered: the agent prompts themselves, and
the PyGithub calls (they need a token and a live PR).

Routing quality is measured separately by `backend/evals/` — two sets of 20, one
tuned against and one held out. As-shipped security recall is **100% on the
held-out set**; router-only is 89%. Performance routing is the weak spot at 43%.
Details and caveats in the [README](../README.md).

---

## Deployment

### What is left

The image is built and verified locally. These steps have to be done by hand:

- [ ] Render → **New → Blueprint**, point it at this repo (it reads `render.yaml`)
- [ ] Set `GROQ_API_KEY` in the dashboard
- [ ] Open the URL and run the bundled CSS sample — it should route to **no auditor**
- [ ] Update `GUARDIAN_CORS_ORIGINS` to the real service URL
- [ ] Optional, for the PR bot: `GITHUB_TOKEN` + `GITHUB_WEBHOOK_SECRET`, then point a
      repo webhook at `/webhook/github`
- [ ] Put the live URL in the README

### One service, not two

`Dockerfile` at the repo root builds the React app and hands the bundle to FastAPI,
which serves it from the same origin as the API. `render.yaml` deploys exactly that.

This replaced an earlier split plan (backend on Render, frontend on Cloudflare Pages).
A split needs CORS configured, a second deploy to keep in sync, and a second service to
keep awake — and `VITE_API_URL` baked at build time is precisely the thing that drifts
when the backend URL changes. Same-origin removes all three problems, and `api.js`
already defaults to a relative `/api`, so no frontend code changed.

The SPA keeps its page in the URL **hash**, so `StaticFiles(html=True)` is all the
fallback needed — there is no path-based route for the server to 404 on.

**Measured before choosing the free plan:** 73 MB resident after a real review, image
334 MB, against Render free's 512 MB limit. Worth stating because the sibling
Adaptive CRAG project had to leave Render for exactly this reason — it peaks at 698 MB
once the cross-encoder loads. Code Guardian has no embedding model and no reranker, so
it fits with room to spare.

There is no database in the blueprint: a review is one graph invocation holding no
state between requests, and the PR bot writes its results back to GitHub rather than
to a store of its own.

### Alternatives

**Cloudflare Workers will not work for the backend** — Python/FastAPI and a
long-running webhook process do not fit that runtime.

Hugging Face Spaces is a viable single-container alternative (Docker SDK, free,
secrets in Settings), with two caveats: free Spaces sleep after inactivity, and a
public Space exposes `/api/review` to anyone, which spends your Groq quota.

### GitHub webhook

1. Repo Settings → Webhooks → Add webhook.
2. Payload URL: the deployed backend's `/webhook/github`.
3. Content type: `application/json` — **not** form-urlencoded, or the signature
   will not match.
4. Events: *Let me select individual events* → **Pull requests** only (untick
   Pushes).
5. Secret: generate with `openssl rand -hex 32` and put the **same** value in the
   backend's `GITHUB_WEBHOOK_SECRET`. This is not optional — without it the
   endpoint returns 503 and processes nothing (fail closed).
6. Also set `GITHUB_TOKEN` (repo scope), or the bot can accept deliveries but
   cannot read the PR.
7. GitHub sends a `ping` immediately. Recent Deliveries should show
   `202 {"status":"pong"}` — the fastest confirmation that both sides hold the
   same secret.
