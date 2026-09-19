# Roadmap — what is built, what is left, what is deliberately deferred

This is the single source of truth for status. The README's roadmap table
summarises it; [TECHNICAL_SPEC §7](TECHNICAL_SPEC.md) details the deferred items.

---

## Current status

| # | Phase | State |
|---|---|---|
| 1 | **Local Code Review Studio** — LangGraph nodes, tool-calling supervisor, `/api/review`, React UI | ✅ done |
| 2 | **GitHub PR Bot** — HMAC webhook, PyGithub client, PR comment | ✅ done |
| 2a | Verification against a real GitHub repo/PR | ⬜ **blocked on a live PR** |
| 2b | Static analysis (Bandit) fused into `security_audit` | ✅ done |
| 2c | Risk score on every review | ✅ done |
| 2d | Test Generation Agent | ✅ done |
| 2e | GitHub Check Run status (gates merges on the risk score) | ✅ done |
| 2f | Streaming (`/api/review/stream`), model gateway fallback, token/cost tracking, JSON logging | ✅ done |
| 2g | Cross-review memory — episodic, semantic, long-term (`app/memory/`) | ✅ done |
| 2h | **Deployed** — Cloud Run, `asia-south1`, auto-deploy on push to `main` | ✅ [live](https://code-guardian-906520260355.asia-south1.run.app) |
| 3, 5 | Advanced Intelligence Layer, full CI/CD | ⬜ deliberately deferred |

**Built although it was not in the plan:** a routing eval with a **held-out set**
(`backend/evals/`, 40 cases), 161 unit tests, and the full docs set.

---

## Verified numbers

Everything here was actually run, not claimed.

| Check | Result |
|---|---|
| Unit tests | **161 pass**, no API key needed |
| **Deployed service, live** | A real review against the Cloud Run URL: **5 findings** (SQL injection, repeated DB connection, unclosed connection, missing index, `SELECT *`), risk **50/high**, **$0.0025** for the request. `/api/health` reports `groq_key_configured: true` and the fallback model configured — the Secret Manager binding and the gateway both work in production, not just locally |
| Episodic memory, live | The same SQL-injection snippet reviewed twice against live Groq: `memory_note` empty on the first pass, `"seen 1 time(s) before (1 fixed)"` on the second — persisted across a full container rebuild via the named Docker volume. |
| Routing eval, **held-out** (20 cases, never tuned against) | as-shipped security recall **100%**, 0 false negatives; router-only 89%; performance 43% |
| Routing eval, dev (20 cases, tuned against) | as-shipped 100%; router-only 90%; performance 50% |
| Static fusion (vulnerable Python) | 8 raw findings → **5** after dedup; **3 confirmed by both engines**; Bandit found 2 SQLi sites the LLM missed |
| Risk score | vulnerable Python **100/100 critical** · slow JS **10/100 low** · CSS **0/100 none** |
| Failed audit | band `unknown`, "score unavailable", "Audit failed — this code was not checked" |
| Test generation | 88 lines of pytest for 3 findings |
| Router cost contrast | CSS **~0.9s** vs vulnerable Python **~11.4s** |
| Webhook auth | 202 · 401 · 401 · 503 |
| API errors | 503 · 502 · 429 |
| Frontend | production build clean |

**Not verified:** the PR bot against a real repository (needs a live PR), and the
quality of the agent prompts against a labelled dataset — only routing is
measured, not the findings themselves.

The eval numbers are from `openai/gpt-oss-20b`, not the default 120b, because the
120b daily quota was exhausted that day. Re-running on 120b is outstanding.

---

## Remaining work

### 2a — Verification against a real PR ⬜ **blocked**

Needs a live pull request. The token is configured and can read the repo, but the
repo has no PRs yet.

Everything up to the GitHub API call is tested — HMAC, event filtering, file
selection, added-line extraction. **The PyGithub calls themselves are not.**

Steps are in the [README](../README.md#github-pr-bot). After adding the webhook,
GitHub sends a `ping` immediately; Recent Deliveries should show
`202 {"status":"pong"}`, which is the fastest confirmation that both sides hold
the same secret.

The Check Run (2e) is also unverified for the same reason — the code decides the
verdict and 8 tests cover that logic, but the `create_check_run` call itself has
never reached GitHub. The token additionally needs **checks:write**.

---

## Deliberately deferred — and why

These are **not rejected on merit**. Each is its own multi-week project rather
than a node this graph can absorb, and building any of them halfway would cost
the depth-over-breadth property the project rests on.

### Phase 3 — Advanced Intelligence Layer

Code Quality, Dependency/License, Documentation agents.

Technically easy (one `@tool` each), but the value per agent is low and each new
agent lowers routing precision. Test Coverage was promoted out of this phase
(shipped as 2d) precisely because it fitted the existing pattern.

### Phase 4 — Learning & Memory ✅ done (partially — see below)

Shipped as `app/memory/`: episodic (has this exact code shape and finding been
seen before, was it fixed or dismissed), semantic (a finding reported repeatedly
and never fixed, distilled into a stated fact via `consolidate_facts`), long-term
(explicit per-repo preferences via `PUT /api/preferences/{repo}`). SQLite-backed,
not the RAG/vector-DB approach this phase originally implied — see
[docs/CODE_NOTES.md](CODE_NOTES.md) for why: this project has no other database
and Groq has no embeddings API, and the actual similarity question ("is this the
same code shape") is answered exactly by a normalized signature match, not
approximately by a vector search.

**What is still genuinely deferred from the original phase description:**
"historical PR analysis" (mining a repo's full PR history to seed memory before
its first review) and team-specific *rules* as a first-class object separate
from preferences. Both are real projects on top of what exists now, not gaps in
what shipped.

### Phase 5 — Full CI/CD integration

Slack/Discord notifications, auto-created Jira/Linear tickets.

The Check Run gate (2e) is the minimal high-value slice of this phase. The rest is
integration surface, not architecture, and proves nothing in an interview.

### Self-healing patch loop

Generate → apply → run tests → regenerate.

Needs a **sandboxed execution runtime** (no network, escape-proof filesystem,
hard timeout). This is why 2d is generation-only: without a correct sandbox, the
tool would itself become a remote code execution — in a *security* tool.

### Codebase-wide dependency/impact graph

"Who calls this function" — AST/Tree-sitter parsing over multiple files.

Would catch the cross-file vulnerabilities currently missed (an added line
interacting with an untouched one). But repo ingestion is a project in itself.

---

## Known weaknesses, in priority order

Knowing these yourself is the most important thing for an interview.

1. **Performance routing is weak** — 50% on the dev set, 43% held-out. The model
   calls the security auditor on code whose only real problem is performance.
   Unlike security, there is no backstop covering it.
2. **Bandit is Python-only.** Elsewhere the security audit is the LLM alone.
   Semgrep would be one more `_run_*` function of the same shape.
3. **The PR bot has not run against a real repository** (2a).
4. **A single review still holds no state of its own** — `app/memory/` remembers
   *across* reviews (past findings, distilled facts, per-repo preferences), but
   nothing about one review's messages or intermediate graph state survives
   past that request, by design (see TECHNICAL_SPEC.md).
5. **20 cases per eval set is small** — the interval around 100% is wide, and the
   cases are self-written and self-labelled.
6. **Eval numbers are from 20b, not the default 120b.**

---

## If there is more time — priority order

| # | Task | Effort | Why |
|---|---|---|---|
| 1 | **2a** — run against a real PR (and see the Check Run land) | 30 min | makes the "real automation" claim true |
| 2 | Re-run the eval on 120b | 20 min | current numbers are from 20b |
| 3 | **Semgrep** for multi-language scanning | 2–3 hrs | removes the Bandit-only limitation |
| 4 | Findings-quality eval (labelled vulnerabilities) | 1 day | only routing is measured today, not findings |
| 5 | Cost/token tracking | 3 hrs | there is currently no cost number worth quoting |

**1 is worth doing before an interview** — it is the only "not verified" caveat
left. 2 closes the last caveat on the headline number.

---

## Deployment ✅

**Live:** https://code-guardian-906520260355.asia-south1.run.app

Google Cloud Run, `asia-south1`, built from the root `Dockerfile` by Cloud Build on
every push to `main`. One service serves both the API and the SPA, so there is no
second thing to deploy and no CORS to configure.

| Setting | Value | Reason |
|---|---|---|
| Memory | 512 MiB | measured peak is 73 MB |
| CPU | 1 | |
| Concurrency | 10 | the default 80 would OOM an LLM service |
| Timeout | 300s | a vulnerable-Python review takes ~11s plus Groq throttling |
| Min instances | 0 | idle costs nothing; the trade is a cold start |
| Max instances | 3 | caps the blast radius if the URL gets hammered |

`GROQ_API_KEY` is injected from Secret Manager, not set as a plain environment
variable. Details and the full click-path are in `../../DEPLOYMENT.md`.

**Cloudflare Workers were ruled out** — Python/FastAPI and a long-running webhook
process do not fit that runtime. Render would fit this project (73 MB against its
512 MB cap) but not the sibling adaptive-crag (698 MB), so Cloud Run was chosen to
keep all three on one platform.

Still worth doing: `GITHUB_TOKEN` and `GITHUB_WEBHOOK_SECRET` are not set on the
deployed service, so the PR bot is inactive there. The review UI works fully; the
webhook fails closed with a 503, which is the intended behaviour rather than a bug.
