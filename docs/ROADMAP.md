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
| 2e | GitHub Check Run status (gate merges on the risk score) | ⬜ next |
| 3–5 | Advanced Intelligence, Learning & Memory, full CI/CD | ⬜ deliberately deferred |

**Built although it was not in the plan:** a routing eval with a **held-out set**
(`backend/evals/`, 40 cases), 99 unit tests, and the full docs set.

---

## Verified numbers

Everything here was actually run, not claimed.

| Check | Result |
|---|---|
| Unit tests | **99 pass**, no API key needed |
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

Steps are in the [README](../README.md#github-pr-bot-phase-2). After adding the
webhook, GitHub sends a `ping` immediately; Recent Deliveries should show
`202 {"status":"pong"}`, which is the fastest confirmation that both sides hold
the same secret.

### 2e — GitHub Check Run ⬜ next

`pr_bot.py` already has an authenticated PyGithub client, and the risk score is
already computed. One more API call:

```
conclusion = "failure"          if risk.band in ("high", "critical")
             "action_required"  if not risk.complete
             "success"          otherwise
```

**`action_required` matters:** on an incomplete review `success` is dangerous
(nothing actually looked) and `failure` is wrong (nothing is known). "A human
should look" is the correct answer.

This turns "posts a comment" into "can gate a merge" without touching the review
graph.

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

### Phase 4 — Learning & Memory

Feedback loop, team-specific rules via RAG, historical PR analysis.

Needs persistent storage, embeddings and a feedback-capture mechanism. The review
graph is **stateless** today — this is an architecture change, not an addition.

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
4. **No persistence** — every review is stateless.
5. **20 cases per eval set is small** — the interval around 100% is wide, and the
   cases are self-written and self-labelled.
6. **Eval numbers are from 20b, not the default 120b.**

---

## If there is more time — priority order

| # | Task | Effort | Why |
|---|---|---|---|
| 1 | **2a** — run against a real PR | 30 min | makes the "real automation" claim true |
| 2 | **2e** — Check Run gate | 1–2 hrs | comment → merge gate; the score already exists |
| 3 | Re-run the eval on 120b | 20 min | current numbers are from 20b |
| 4 | **Semgrep** for multi-language scanning | 2–3 hrs | removes the Bandit-only limitation |
| 5 | Findings-quality eval (labelled vulnerabilities) | 1 day | only routing is measured today, not findings |
| 6 | Cost/token tracking | 3 hrs | there is currently no cost number worth quoting |

**1 and 2 are worth doing before an interview.** 3 closes the last caveat on the
headline number.

---

## Deployment

Details in [BUILD_AND_DEPLOY.md](BUILD_AND_DEPLOY.md). Short version:

| Part | Platform |
|---|---|
| Backend (FastAPI + Docker) | Render / Railway |
| Frontend (React) | Cloudflare Pages / Vercel |

**Cloudflare Workers will not work for the backend** — Python/FastAPI and a
long-running webhook process do not fit that runtime.

Before deploying: verify `GUARDIAN_MODEL` (Groq retires ids), set
`GITHUB_WEBHOOK_SECRET` (or the webhook fails closed with 503), and add the
deployed frontend URL to `GUARDIAN_CORS_ORIGINS`.
