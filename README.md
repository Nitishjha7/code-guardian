# Code Guardian

**Multi-Agent Autonomous Code Reviewer & PR Bot**

Code Guardian is a multi-agent code auditing platform. It coordinates specialized LangGraph agents — Security, Performance, and Patch Generator — to review code or pull requests, flag vulnerabilities and inefficiencies, and autonomously generate production-ready fixes, all validated through Guardrails AI before being posted back as a GitHub PR review.

> ## Status: Phases 1 and 2 implemented
>
> | Piece | State |
> |---|---|
> | Docs — 9 files: walkthrough, spec, code notes, code Q&A, interview notes, fundamentals, roadmap, setup, build & deploy | ✅ complete |
> | LangGraph graph, tool-calling supervisor, 3 agents, guardrails | ✅ implemented |
> | FastAPI `/api/review`, `/api/review-pr`, `/api/health`, `/api/graph` | ✅ implemented |
> | React dashboard — sidebar, risk donut, agent cards, side-by-side patch, history | ✅ implemented |
> | Docker images + Compose stack | ✅ builds and runs |
> | Phase 2: GitHub PR bot — `/webhook/github`, HMAC auth, PyGithub client | ✅ implemented |
> | 2b static analysis · 2c risk score · 2d test generation | ✅ implemented |
> | 2a live PR verification · 2e Check Run gate · Phases 3–5 | ❌ see [ROADMAP](docs/ROADMAP.md) |
>
> **Verified end-to-end against a live Groq key:**
>
> | Check | Result |
> |---|---|
> | 99 backend unit tests | pass |
> | Routing eval, **held-out** set of 20 | as-shipped security recall **100%** (0 false negatives); router-only 89%; performance 43% |
> | Static analysis fusion (vulnerable Python) | 8 raw findings → **5** after dedup; **3 confirmed by both engines**; Bandit added 2 SQLi sites the LLM missed |
> | Risk score across the three samples | vulnerable Python **100/100 critical**, slow JS **10/100 low**, plain CSS **0/100 none** |
> | Risk score on a failed audit | band `unknown`, "score unavailable" — never a reassuring number |
> | Frontend production build | pass |
> | Compose stack (nginx → backend) | `/api/health` + `/api/review` both 200 |
> | Vulnerable Python sample | 5 security + 2 performance findings, 94-line patch, 88 lines of generated tests, ~11.4s |
> | Plain CSS sample | router skipped both auditors, 0.9s |
> | Slow JS sample | router chose performance only, flagged O(u×e) → O(u+e) |
> | Failed audit (dead model id) | reported as **"Audit failed — this code was not checked"**, never as clean |
> | Missing / rejected / rate-limited key | 503 / 502 / 429 |
> | Webhook: valid HMAC / tampered / missing / no secret set | 202 queued / 401 / 401 / 503 |
>
> **Not verified:** the PR bot against a real GitHub repository — that needs a
> `GITHUB_TOKEN` and a live PR. Everything up to the GitHub API call is tested;
> the PyGithub calls themselves are not.

## Tech Stack

- **Agent Orchestrator**: LangGraph (StateGraph) — supervisor pattern built as an LLM **tool-calling router** (`bind_tools` + `ToolNode`): the model decides which specialists a given diff actually needs, instead of a fixed fan-out. Parallel tool execution, state reducers, conditional edge routing. See [§3a of the spec](docs/TECHNICAL_SPEC.md)
- **LLM Engine**: LangChain + Groq (`openai/gpt-oss-120b` by default; any tool-calling model your key can see, set via `GUARDIAN_MODEL`)
- **Static Analysis**: Bandit runs inside the security audit and its findings merge with the LLM's into one list, tagged by `source`. Neither engine subsumes the other — the scanner cannot miss a pattern it has a rule for or hallucinate one it doesn't; the LLM catches what no rule encodes (missing authorization, business-logic flaws) and explains it in context. A finding both engines flag independently is marked `llm+bandit:<rule>` and escalated in severity
- **Safety & Guardrails**: secrets scanning + tone guard on every outbound diff, patch and comment. Guardrails AI is used when installed; the default is a local pattern scanner, and `guardrail_report.engine` always names which one ran — see [Build & Deploy](docs/BUILD_AND_DEPLOY.md) for why
- **Tooling Layer**: PyGithub — fetches PR diffs, posts review comments (not the GitHub MCP server; [why](docs/BUILD_AND_DEPLOY.md))
- **Backend**: FastAPI (async) — REST API + HMAC-authenticated GitHub webhook listener
- **Frontend**: React + Tailwind + Monaco — dashboard with a risk donut, per-agent finding cards, side-by-side patch, generated tests, the agent log, and analytics built from this browser's own review history. Pages that need a GitHub token say so instead of showing placeholder data
- **Deployment**: Docker & Docker Compose

## Project Structure

```
backend/app/graph.py           # LangGraph state machine (nodes + edges)
backend/app/state.py           # ReviewerState schema
backend/app/config.py          # Settings + shared LLM factory
backend/app/main.py            # FastAPI: review, review-pr, health, graph, webhook
backend/app/agents/            # Security, Performance, Patch Generator, Supervisor
backend/app/agents/static_analysis.py   # Bandit fusion: scan, map, dedupe, merge
backend/app/guardrails_config/ # Secrets + tone validators on all outbound text
backend/app/pr_bot.py          # Phase 2: HMAC verification + PR review orchestration
backend/app/mcp_clients/       # GitHub client (PyGithub): PR diffs, comments
backend/app/risk.py            # Weighted risk score (findings + size, corroboration-aware)
backend/app/agents/test_generator.py    # Regression tests (generated, never executed)
backend/tests/                 # 99 unit tests for the LLM-free seams
backend/evals/                 # 40 labelled snippets: 20 dev + 20 held-out
frontend/src/components/       # Shell, ReviewPanel, AgentFindings, PatchView
frontend/src/pages/            # Agents, Analytics, Settings, token-gated pages
frontend/src/lib/              # Shared palette + browser-local review history
docs/                          # 9 docs — start with PROJECT_WALKTHROUGH.md
```

## Quick start

You need a free Groq API key from https://console.groq.com/keys.

```bash
cp backend/.env.example backend/.env
# edit backend/.env and set GROQ_API_KEY=gsk_...

docker compose up --build
```

- UI: http://localhost:3000
- API: http://localhost:8010/api/health (interactive docs at `/docs`)

The backend is published on host port **8010** (`"8010:8000"` in
`docker-compose.yml`) because 8000 is commonly already taken. Change that host
side if you prefer another port; the frontend reaches the backend over the
compose network, so nothing else needs updating.

### Running without Docker

```bash
# backend
cd backend
python -m venv .venv && source .venv/bin/activate    # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000

# frontend (second terminal)
cd frontend
npm install
npm run dev        # http://localhost:5173, proxies /api to :8000
```

### Tests

The tests cover the deterministic seams — response parsing, diff generation,
routing, the state collector, the guardrails, and the whole webhook surface
(HMAC verification, event filtering, file selection), and the static-analysis
fusion (severity mapping, line extraction, dedup) — so they run without an
API key, a GitHub token, or a single LLM call.

```bash
cd backend && pip install pytest && pytest -q
# or, with no local Python:
docker build -f backend/Dockerfile.test -t code-guardian-test backend && docker run --rm code-guardian-test
```

## Demo script

The UI ships three samples (top-left dropdown) chosen to make the router's
decision visible:

| Sample | Observed behaviour |
|---|---|
| Vulnerable Python (SQLi + N+1) | Both auditors run (the high-stakes backstop forces them). 5 security findings — 3 marked **`confirmed`** because Bandit flagged the same line independently, and 2 SQLi sites only Bandit caught. Risk **100/100 critical**, 94-line patch, 88 lines of generated regression tests. **~11.4s** |
| Plain CSS | Router calls **no auditor at all** and the UI shows both sections as "not run". **~0.9s** — the cost difference *is* the demo |
| Slow JavaScript | Router calls **performance only**; flags the quadratic join `O(u × e)` → `O(u + e)` |

Every review opens with a **risk score** (0–100 plus a band), computed once in
`collect_node` and read identically by the report, the API, the UI and the PR
comment. Weights are calibrated against the bands rather than picked for
roundness: one Critical finding reaches *high*, two reach *critical*, because a
single remotely exploitable vulnerability has to be enough to stop a merge once
the Check Run gate (2e) reads this number. Findings dominate — diff size is
capped at a +25% modifier, so a 2000-line clean diff still scores 0 — and
findings both engines confirmed weigh 1.25×. Across a PR the bot reports the
**worst file's** score, not an average: a PR is as risky as its most dangerous
change.

Three things to show beyond the findings:

- **The risk score on a failed audit.** It reports band `unknown` and "score
  unavailable", never 0/none. A number computed from findings that were never
  collected would be the silent-pass bug wearing a friendlier face.
- **The "Force full audit" checkbox** — the §3a override. It bypasses routing
  and runs every auditor, for high-stakes paths where a false negative is worse
  than wasted tokens.
- **The failure banner.** Set `GUARDIAN_MODEL` to a nonsense id and re-run: the
  review comes back marked *"This review is incomplete — audit failed, this code
  was not checked"*, not as a clean pass. An auditing tool that silently reports
  "no issues" when it never ran is worse than no tool, so that path is tested.

## Routing eval — does the router actually work?

§3a of the spec argues the supervisor should route instead of fanning out, and
names the risk: a false negative (skipping the security audit on code that
needed one) is far worse than the tokens a static fan-out would have wasted.
`backend/evals/` turns that from a claim into a number — **two** sets of 20
labelled snippets, each marked for whether a competent reviewer would consider
each audit worth paying for.

There are two sets because the first one stopped being trustworthy the moment it
was useful:

- **`routing_cases.py` (dev)** — used to *tune* the tool docstrings. Performance
  recall moved 33% → 50% that way, which makes its numbers optimistic.
- **`routing_cases_holdout.py` (held-out)** — never tuned against, and
  deliberately harder: Go, Java, SQL and shell instead of the Python and JS the
  docstrings were written for, plus no-audit cases that contain *token*, *auth*
  and *query* in harmless positions, because the backstop keys off exactly those
  words. The file's rule is that **a failing case changes neither the case nor
  the prompt it failed on** — a held-out set you edit after seeing the score is
  just a slower dev set.

```bash
cd backend && python -m evals.run_routing_eval --set both --mode both
# or: docker build -f backend/Dockerfile.eval -t cg-eval backend \
#     && docker run --rm --env-file backend/.env cg-eval --set holdout
```

Measured on `openai/gpt-oss-20b`, 20 cases per set:

| Set | Mode | Security recall | Security precision | Performance recall |
|---|---|---|---|---|
| dev (tuned against) | `router-only` | 90% | 82% | 50% |
| dev (tuned against) | `as-shipped` | **100%** | 77% | 67% |
| **held-out** | `router-only` | **89%** | 80% | 43% |
| **held-out** | `as-shipped` | **100%** | 60% | 57% |

Read honestly, that says four things:

- **As-shipped security recall is 100% on data never tuned against.** This is
  the number the design stakes itself on, and it survives contact with a fresh
  set. It is the only claim here worth making loudly.
- **The dev/held-out gap is one point on security** (90 → 89). The docstring
  tuning generalised rather than overfitting — which is not something you get to
  assume, only something you get to check.
- **Performance recall is the weak spot, and worse on held-out** (50% → 43%).
  The model calls the security auditor on code whose only real problem is
  performance. Tolerable only because the errors are asymmetric: a missed
  performance audit costs an optimization suggestion, a missed security audit
  costs a vulnerability.
- **The backstop trades precision for safety, visibly.** It lifts security
  recall to 100% but drops precision to 60% on held-out — it fires on anything
  with an auth/DB/exec keyword. That is the intended trade (a false positive
  costs cents), now quantified rather than assumed.

The exit code fails when as-shipped security recall drops below 100%
(`--min-security-recall`), and when the held-out set was run the gate reads
*its* number, because that is the only one not contaminated by tuning. A run
where fewer than 80% of cases reached the model reports **no score at all** and
exits non-zero — a routing number computed from cases that never ran would be
fiction, which is the same rule the review graph follows.

> **Remaining caveats:** 20 cases per set is small, so the interval around 100%
> is wide; the cases are self-written and self-labelled; and these numbers are
> from `gpt-oss-20b` rather than the default `gpt-oss-120b`, because the 120b
> daily quota was exhausted that day. Re-running on 120b is outstanding.

## What the dashboard shows — and what it deliberately doesn't

The UI is built to look like a tool, not a landing page. There is no hero
banner, no tagline, no "AI agents working together" card, no gradient — those
read as filler in something you are supposed to work in, and they are the
tell that a UI was generated rather than designed. Five nav items, all of which
do something. Anything that would have been decoration was deleted instead of
styled.

Every number on screen comes from a review that actually ran:

- **Risk donut, agent cards, patch, tests, agent log** — straight from the review.
- **Recent Activity and Analytics** — built from `localStorage`, because the backend is
  stateless by design (persistence is Phase 4). They are real, but they live in this
  browser only: clearing site data wipes them, and they do not follow you to another
  machine.
- **`confirmed` badges** mark findings both the LLM and Bandit flagged independently.
- **Pull Requests** says what it needs (`GITHUB_TOKEN`) rather than rendering
  placeholder rows. A "Repository" page was removed outright — repo-wide review is
  not built, and a nav item that leads nowhere is worse than a missing one.
- **No cost-per-review tile.** It has not been measured, and this project does not
  display numbers it has not measured.

`POST /api/review-pr` reviews a pull request on demand and **posts nothing** — it
returns the comment it *would* post, for preview. Only the webhook writes to a
repository, because reading a PR and commenting on it are different levels of
consequence.

## GitHub PR bot (Phase 2)

When a pull request is opened or updated, the bot reviews **the lines that PR
adds** — not the whole file — and posts one aggregated comment.

```bash
# in backend/.env
GITHUB_TOKEN=ghp_...              # needs repo scope (or Contents+PR read/write on a fine-grained token)
GITHUB_WEBHOOK_SECRET=<random>    # generate with: openssl rand -hex 32
```

Then in the repo: **Settings → Webhooks → Add webhook**

| Field | Value |
|---|---|
| Payload URL | `https://<your-backend>/webhook/github` |
| Content type | `application/json` |
| Secret | the same `GITHUB_WEBHOOK_SECRET` |
| Events | *Let me select individual events* → **Pull requests** |

Behaviour worth knowing:

- **Fails closed.** If `GITHUB_WEBHOOK_SECRET` is unset the endpoint returns 503
  and processes nothing. A public URL that runs LLM calls and writes comments is
  a denial-of-wallet vector, so "I forgot the secret" must not become "anyone can
  drive this bot". Signatures are compared with `hmac.compare_digest`.
- **Returns 202 immediately**, reviews in the background. GitHub abandons a
  delivery after 10s; a real review takes longer, and an inline review would make
  every PR look like a failed delivery in the webhook log.
- **Reviews only what it should.** Draft PRs are skipped until marked ready;
  `closed`/`labeled`/`assigned` events are ignored; lockfiles, minified bundles,
  `node_modules/`, `vendor/`, `dist/` and migrations are filtered out; the file
  count is capped at 10, ranked by additions so the cap drops trivia, not
  substance.
- **A file whose review crashes is reported as a failed audit**, not omitted —
  the same rule as the local studio.

Locally you can exercise it without GitHub:

```bash
SECRET=test-secret-123
BODY='{"action":"opened","repository":{"full_name":"acme/widgets"},"pull_request":{"number":42,"draft":false,"head":{"sha":"abc"}}}'
SIG="sha256=$(printf '%s' "$BODY" | openssl dgst -sha256 -hmac "$SECRET" | awk '{print $NF}')"
curl -X POST http://localhost:8010/webhook/github \
  -H "X-GitHub-Event: pull_request" -H "X-Hub-Signature-256: $SIG" \
  -H "Content-Type: application/json" -d "$BODY"
```

## Docs

**Start here → [Project Walkthrough](docs/PROJECT_WALKTHROUGH.md)** — the whole project
in one file: flowchart, how each piece was built and why, what was verified, and the
five bugs only real runs found.

| Doc | What it is for |
|---|---|
| [PROJECT_WALKTHROUGH](docs/PROJECT_WALKTHROUGH.md) | the whole system, end to end — read this one first |
| [TECHNICAL_SPEC](docs/TECHNICAL_SPEC.md) | architecture, graph topology, §3a routing argument, deviations from spec |
| [CODE_NOTES](docs/CODE_NOTES.md) | file-by-file "why this exists", not "what it does" |
| [CODE_QA](docs/CODE_QA.md) | 35 questions to defend your own code, with answers |
| [INTERVIEW_NOTES](docs/INTERVIEW_NOTES.md) | pitch, trade-offs, limitations, demo script, honesty checklist |
| [AGENT_FUNDAMENTALS](docs/AGENT_FUNDAMENTALS.md) | general agent / tool-calling / eval concepts + question bank |
| [ROADMAP](docs/ROADMAP.md) | what is done, what is left, what is deferred and why |
| [SETUP](docs/SETUP.md) | prerequisites, env, local dev, troubleshooting table |
| [BUILD_AND_DEPLOY](docs/BUILD_AND_DEPLOY.md) | build priorities and deployment (Render/Railway + Cloudflare Pages) |

## Roadmap

| # | Phase | State |
|---|---|---|
| 1 | **Local Code Review Studio** — LangGraph nodes, tool-calling supervisor, `/api/review`, React UI | ✅ done |
| 2 | **GitHub PR Bot** — webhook-triggered reviews posted as PR comments | ✅ done |
| 2a | Real GitHub repo/PR verification (token + webhook against a live PR) | next up |
| 2b | **Static analysis (Bandit) fused into `security_audit`** — findings from both engines merged into one list, tagged by source | ✅ done |
| 2c | **Risk score on every review** — one number, calibrated so a single Critical blocks a merge | ✅ done |
| 2d | Test Generation Agent — one more `@tool` emitting a regression test per finding | planned |
| 2e | GitHub Check Run status (gate merges on risk score) | planned |
| 3–5 | Advanced Intelligence Layer, Learning & Memory, full CI/CD Integration | roadmap, deliberately deferred |

Adding an agent is one more `@tool` with a clear docstring — the graph
topology does not change, which is the whole point of the supervisor pattern
(§3a). That's why 2b–2e are scoped the way they are: each fits inside the
existing graph with no new infrastructure. Phases 3–5 in their original form
(repo-wide RAG, a dependency/impact graph, sandboxed patch validation,
vector-DB team memory) stay deliberately deferred — each is its own
multi-week project, not a node this graph can absorb. Depth over breadth was
the explicit call; see [docs/BUILD_AND_DEPLOY.md](docs/BUILD_AND_DEPLOY.md).

Full details, including what's deferred and why, in
[docs/TECHNICAL_SPEC.md §7](docs/TECHNICAL_SPEC.md#7-future-phases).
