# Build & Deploy

How the project was scoped and how it is deployed. Architecture is in
[TECHNICAL_SPEC.md](TECHNICAL_SPEC.md); the build narrative in
[PROJECT_WALKTHROUGH.md](PROJECT_WALKTHROUGH.md).

## Scope

Depth over breadth. Three or four pieces built properly, with their limits
measured and written down, beat a dozen half-finished ones — so Phases 3–5 exist
as a reasoned [roadmap](ROADMAP.md) rather than as shallow implementations.

### What was built, and why it came first

- **LangGraph multi-agent graph** — Security, Performance and Patch Generator
  wired through `StateGraph`. The core of the system.
- **Tool-calling supervisor** — deliberately not a fixed fan-out. The specialists
  are exposed as `@tool`, bound with `llm.bind_tools([...])`, and looped via
  `ToolNode` plus a conditional edge. This is the one place where the *model*
  decides control flow rather than a graph edge, which is the project's central
  argument — see [TECHNICAL_SPEC §3a](TECHNICAL_SPEC.md).
- **FastAPI backend** — `/api/review` accepts a submission and drives the graph.
- **React UI** — editor, review trigger, result cards, live run trace.
- **Output guardrails** — every outbound diff and comment is scanned for
  credentials before it leaves.
- **A real state schema** — separated nodes, explicit reducers, and the
  `ok`/`error` envelope that keeps a failed audit distinct from a clean one.

### Built beyond the original scope

- **GitHub PR bot** — a webhook listener that reviews the lines a pull request
  adds and posts a comment. Verified on a real PR; setup in the
  [README](../README.md#github-pr-bot).
- **Held-out routing eval** — 40 labelled cases across two sets, one never tuned
  against, with the exit code gated on recall.
- **Streaming, an LLM gateway, token/cost tracking and structured logging** —
  each added in response to something the project actually hit.

### Deliberately deferred

Phases 3–5 (extra specialist agents, a feedback loop with vector memory, full
CI/CD integration) are documented in [ROADMAP.md](ROADMAP.md) with the reasoning
for each. Each is its own multi-week project rather than a node this graph can
absorb.

## Groq retires model ids

`llama-3.3-70b-versatile` (in the original spec) no longer exists on Groq — it
404s. Check first:

```bash
curl https://api.groq.com/openai/v1/models -H "Authorization: Bearer $GROQ_API_KEY"
```

Put a working id in `GUARDIAN_MODEL`. The default is `openai/gpt-oss-120b`, and
**it must support tool calling** — the supervisor depends on it.

Also watch the daily token quota. The free tier is 200k tokens/day *per model*;
heavy testing will exhaust it. Switching to
`openai/gpt-oss-20b` uses a separate bucket.

## Build order (status)

1. ✅ `backend/app/graph.py` — `StateGraph` + `ReviewerState` (in `state.py`)
2. ✅ `agents/security_agent.py` + `performance_agent.py` — focused prompts
3. ✅ `agents/patch_generator.py` — synthesize findings into a diff
4. ✅ `guardrails_config/` — secrets + tone guard on all outbound text
5. ✅ FastAPI `/api/review` wiring the graph (`app/main.py`)
6. ✅ React frontend — editor, findings, patch, tests, agent log
7. ✅ GitHub PR bot — `/webhook/github` with HMAC auth, `pr_bot.py`
8. ✅ Bandit fusion, risk score, test generation, held-out routing eval

## Method

Built stage by stage in the order above, with each stage run against the real Groq
API before the next one started. That ordering was not incidental — three of the
six decisions documented below were only discovered *because* a stage was exercised
for real rather than assumed to work. The failed-audit bug, in particular, was
invisible until a retired model id made every audit 404 at once.

Implementation was done with AI assistance, which is worth naming plainly because
it changes what the interesting work actually was. Generating a LangGraph node or a
React card is no longer the hard part. The research and the judgement calls are:

**Architecture** — a tool-calling supervisor that *routes* was chosen over the more
common static fan-out, after reading how ReAct-style loops behave when the model
owns control flow. The trade is real: routing can under-call, which is why
`looks_high_stakes()` exists as a deterministic backstop.

**Evaluation design** — routing accuracy is a claim, so it needed a measurement. A
second set of 20 cases was written and **never tuned against**, and the rule that a
failing case may change neither itself nor the prompt it failed on was set before
any numbers were read. That constraint is what makes the 100% held-out recall worth
quoting; without it the number would be training signal.

**Failure semantics** — deciding that *"did not run"* must be a distinct state from
*"ran and found nothing"*, and that a review with a failed audit is `unknown` rather
than `0/100`. That is a domain judgement about auditing tools, not a coding task.

**Knowing what not to claim** — the `mcp_clients/` folder runs PyGithub, and the
docs say so rather than letting the folder name imply an MCP integration that does
not exist. Similarly, `guardrail_report.engine` always names the engine that
actually ran.

**Measurement over assertion throughout** — 73 MB peak memory, 698 MB on the
sibling project, 4 calls vs 1 on the routing contrast, $0.0025 per review. Every
number in these docs came from running the thing, and the ones that could not be
measured are marked as unmeasured.

The sections below are where each of those decisions is set out in full.

## Where the implementation departs from the obvious reading

Six deliberate decisions, each with a reason worth recording.

- **A failed audit is never rendered as "no issues found".** This was a real bug.
  The audits are tools, and LangGraph's `ToolNode` turns an uncaught exception
  into a plain ToolMessage — so when the Groq model id was retired and every
  audit 404'd, the system reported **0 findings on code with a Critical SQL
  injection**. For an auditing tool that is the worst possible failure: silence
  became indistinguishable from a pass. Fixed with a `{"ok": bool, ...}` envelope
  per tool, `failed_audits` / `audit_errors` in state, and a report that leads
  with an "incomplete review" banner. Four tests pin it down. The general form of
  the lesson: an agent's output is only trustworthy if *"did not run"* is a
  distinct state from *"ran and found nothing"*.

- **The diff is computed with `difflib`, not asked for from the LLM.** Models
  emit unified diffs with wrong hunk headers and line counts, and such a patch
  will not apply. The model returns the rewritten file; the diff is derived from
  the two texts, exact by construction.

- **Guardrails AI is optional; a local pattern scanner is the default.** Some
  `guardrails-ai` hub validators pull a full torch install — a bad trade for a
  container that otherwise fits in a few hundred MB. The fallback is a real
  guard (11 secret patterns, placeholder-aware so it does not flag the
  `os.environ[...]` a fix is *supposed* to emit), and `guardrail_report.engine`
  always names which engine ran — so the report never implies a validator that
  did not execute.

- **The "MCP client" layer is PyGithub, not an MCP server.** The folder is named
  `mcp_clients/` after the original spec, and the name is misleading enough to be
  worth stating outright. Running a real MCP server here would mean a second
  container wrapping REST calls this backend already makes, and MCP's actual
  value — a *model* discovering and calling tools at runtime — does not apply to
  fixed, webhook-driven calls. The runtime tool discovery in this project is in
  `supervisor.py`, not here.

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

**172 tests, no API key needed.** Not covered: the agent prompts themselves, and
the PyGithub calls (they need a token and a live PR).

Routing quality is measured separately by `backend/evals/` — two sets of 20, one
tuned against and one held out. As-shipped security recall is **100% on the
held-out set**; router-only is 89%. Performance routing is the weak spot at 43%.
Details and caveats in the [README](../README.md).

---

## Deployment

### Live

**https://code-guardian-906520260355.asia-south1.run.app**

Google Cloud Run, region `asia-south1` (Mumbai — ~10ms from India against ~150ms from
the `europe-west1` default). Cloud Build watches `main` and redeploys on every push,
so deployment is a `git push`, not a separate step.

Verified on the live URL, not locally: a real review returned **5 findings** at risk
**50/high** for **$0.0025**, and `/api/health` reports `groq_key_configured: true`
with the fallback model configured.

### Why Cloud Run over Render

Render would fit *this* project — 73 MB resident against its 512 MB free cap, with
room to spare. It does not fit the sibling Adaptive CRAG, which peaks at **698 MB**
once the cross-encoder loads. Cloud Run lets memory be chosen per service (128 MiB to
32 GiB), so all three portfolio projects live on one platform instead of being split
across providers for no reason other than a memory ceiling.

`render.yaml` is still in the repo and still correct — it is a working blueprint for
anyone who wants to deploy this elsewhere. It is simply not what runs today.

### The settings, and why each one

| Setting | Value | Reason |
|---|---|---|
| Memory | 512 MiB | 73 MB measured peak — a wide margin, not a guess |
| CPU | 1 | |
| Concurrency | **10** | The Cloud Run default is 80. Eighty parallel LLM requests would OOM a 512 MiB container; the app's own `anyio.CapacityLimiter(4)` caps real parallelism far below that anyway |
| Request timeout | 300s | A vulnerable-Python review takes ~11s, plus whatever Groq's throttling adds |
| Min instances | **0** | Idle costs nothing. The console suggests raising it to 1 "to reduce cold starts" — that is a ~₹800–1,500/month line for a permanently warm container, and not worth it for a portfolio demo |
| Max instances | 3 | Caps the bill if the public URL is hammered |
| Container port | 8080 | Cloud Run injects `PORT=8080`; the Dockerfile's `CMD` reads `${PORT:-8000}`. They match — this does not need "fixing" to 8000 |

`GROQ_API_KEY` is injected from **Secret Manager**, not stored as a plain environment
variable. That binding needs an explicit IAM grant
(`roles/secretmanager.secretAccessor` on the default compute service account); without
it the revision fails to start with a permission error. The first two deploy attempts
failed on exactly that.

The container command and arguments are left **blank** on purpose. Filling them
overrides the Dockerfile's `CMD`, which would silently drop `--log-config
logging.json` and take the JSON access logs with it.

### One service, not two

`Dockerfile` at the repo root builds the React app and hands the bundle to FastAPI,
which serves it from the same origin as the API.

This replaced an earlier split plan (backend on Render, frontend on Cloudflare Pages).
A split needs CORS configured, a second deploy to keep in sync, and a second service to
keep awake — and `VITE_API_URL` baked at build time is precisely the thing that drifts
when the backend URL changes. Same-origin removes all three problems, and `api.js`
already defaults to a relative `/api`, so no frontend code changed.

The SPA keeps its page in the URL **hash**, so `StaticFiles(html=True)` is all the
fallback needed — there is no path-based route for the server to 404 on.

### The PR bot, verified on a real pull request

The review API and the webhook path are different integrations. The second one had
never run against a real repository until the service was deployed.

[**PR #1**](https://github.com/Nitishjha7/code-guardian/pull/1) adds
`examples/vulnerable_user_service.py` — SQL injection three ways, shell injection,
`pickle.loads` on untrusted input, `eval()` on caller input, hardcoded credentials, a
leaked file handle. The deployed bot
[reviewed it](https://github.com/Nitishjha7/code-guardian/pull/1#issuecomment-5740503341):

- **Risk 100/100 CRITICAL**, "this should block the merge"
- **11 security / 5 performance** findings, 6 of them Critical
- Bandit's B403 and B404 fused in beside the LLM findings
- A complete suggested patch — parameterised queries, `IN`-clause batching, context
  managers, an allow-list on the report filename

**The guardrail caught the bot's own output.** The patch renders the hardcoded
password as `DB_PASSWORD = "[REDACTED-BY-GUARDRAIL]"` — the outbound scanner stripped
a secret from the comment before it reached a public PR. That path only runs on the
webhook route and had never been exercised for real.

Webhook auth, checked both directions against the live service: correctly signed body
→ **202 `{"status":"pong"}`**, tampered signature → **401 `signature mismatch`**.

Four failures had to be cleared first, none of which reproduce locally: the Secret
Manager IAM grant, a trailing newline in a pasted secret, the webhook's default
`x-www-form-urlencoded` content type (the signature is over the raw body, so the
form encoding breaks it), and request-based billing freezing the background review
task the instant the 202 returned. The last one is the interesting one — it fails
*silently*, with the log ending at `Queued review` and no error after it.

### Two things the deployed service does not do

**The Check Run does not post.** Everything else on the webhook path works — see the
PR bot section below — but `create_check_run` returns 403. GitHub's fine-grained
tokens have no `Checks` permission; it is App-only. A classic PAT with `checks:write`,
or packaging this as a GitHub App, would close it. The bot catches the failure and
posts its review comment regardless, which is the right failure mode: the merge gate
is missing, the review is not.

**Cross-review memory resets on cold start.** A review is still one graph invocation
holding no state of its own between requests, but `app/memory/` persists
episodic/semantic/long-term facts *across* reviews in a SQLite file at
`MEMORY_DB_PATH` (default `/data/memory.db`). Locally, docker-compose mounts a named
volume there so it survives a rebuild. **Cloud Run's filesystem is ephemeral** — it is
destroyed when the service scales to zero, so memory is cold again on the next
request. Nothing crashes; that is `app/memory/`'s fail-open design working as
intended. The practical effect is that memory demonstrates within a warm instance
(two reviews back to back) and not across an idle gap. Closing it means moving the
store to Cloud Storage or Postgres.

### Alternatives considered

**Cloudflare Workers will not work for the backend** — Python/FastAPI and a
long-running webhook process do not fit that runtime.

Hugging Face Spaces is a viable single-container alternative (Docker SDK, free,
secrets in Settings), with two caveats: free Spaces sleep after inactivity, and a
public Space exposes `/api/review` to anyone, which spends the Groq quota behind it.

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
