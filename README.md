# Code Guardian

**Multi-Agent Autonomous Code Reviewer & PR Bot**

Code Guardian is a multi-agent code auditing platform. It coordinates specialized LangGraph agents — Security, Performance, and Patch Generator — to review code or pull requests, flag vulnerabilities and inefficiencies, and autonomously generate production-ready fixes, all validated through Guardrails AI before being posted back as a GitHub PR review.

> ## Status: Phases 1 and 2 implemented
>
> | Piece | State |
> |---|---|
> | Docs (README, spec, setup, build & deploy guide) | ✅ complete |
> | LangGraph graph, tool-calling supervisor, 3 agents, guardrails | ✅ implemented |
> | FastAPI `/api/review`, `/api/health`, `/api/graph` | ✅ implemented |
> | React + Monaco review dashboard | ✅ implemented |
> | Docker images + Compose stack | ✅ builds and runs |
> | Phase 2: GitHub PR bot — `/webhook/github`, HMAC auth, PyGithub client | ✅ implemented |
> | Phases 3–5 (extra agents, memory, CI/CD gating) | ❌ roadmap only, by design |
>
> **Verified end-to-end against a live Groq key:**
>
> | Check | Result |
> |---|---|
> | 71 backend unit tests | pass |
> | Routing eval, 20 labelled cases | security recall **100%** (0 false negatives); performance recall 50% |
> | Static analysis fusion (vulnerable Python) | 8 raw findings → **5** after dedup; **3 confirmed by both engines**; Bandit added 2 SQLi sites the LLM missed |
> | Frontend production build | pass |
> | Compose stack (nginx → backend) | `/api/health` + `/api/review` both 200 |
> | Vulnerable Python sample | 3 security + 4 performance findings, 80-line patch, 6.4s |
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
- **Frontend**: React, Tailwind CSS, Monaco Editor
- **Deployment**: Docker & Docker Compose

## Project Structure

```
backend/app/graph.py           # LangGraph state machine (nodes + edges)
backend/app/state.py           # ReviewerState schema
backend/app/config.py          # Settings + shared LLM factory
backend/app/main.py            # FastAPI: /api/review, /api/health, /api/graph, /webhook/github
backend/app/agents/            # Security, Performance, Patch Generator, Supervisor
backend/app/agents/static_analysis.py   # Bandit fusion: scan, map, dedupe, merge
backend/app/guardrails_config/ # Secrets + tone validators on all outbound text
backend/app/pr_bot.py          # Phase 2: HMAC verification + PR review orchestration
backend/app/mcp_clients/       # GitHub client (PyGithub): PR diffs, comments
backend/tests/                 # 71 unit tests for the LLM-free seams
backend/evals/                 # 20 labelled snippets measuring routing recall
frontend/src/                  # React + Monaco review dashboard
docs/                          # Setup, technical spec, build & deploy
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
| Vulnerable Python (SQLi + N+1) | Both auditors run (the high-stakes backstop forces them). 5 security findings — 3 of them marked **`confirmed`** because Bandit flagged the same line independently, and 2 SQLi sites only Bandit caught. N+1 queries `O(n)` → `O(1)`, missing index, unclosed connection. **~7.4s** |
| Plain CSS | Router calls **no auditor at all** and the UI shows both sections as "not run". **~0.9s** — the cost difference *is* the demo |
| Slow JavaScript | Router calls **performance only**; flags the quadratic join `O(u × e)` → `O(u + e)` |

Two things to show beyond the findings:

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
`backend/evals/` turns that from a claim into a number — 20 labelled snippets,
each marked for whether a competent reviewer would consider each audit worth
paying for.

```bash
cd backend && python -m evals.run_routing_eval
# or: docker build -f backend/Dockerfile.eval -t cg-eval backend \
#     && docker run --rm --env-file backend/.env cg-eval
```

Measured on `openai/gpt-oss-120b`, 20 cases:

| Mode | Security recall | Security precision | Performance recall | Performance precision |
|---|---|---|---|---|
| `router-only` (LLM judgement alone) | **100%** | 83% | 50% | 100% |
| `as-shipped` (router + high-stakes backstop) | **100%** | 83% | 67% | 33% |

Read honestly, that says three things:

- **Security recall is 100% — zero missed security audits.** This is the number
  the design stakes itself on, and it holds with and without the backstop.
- **Performance recall is the weak spot (50% router-only).** On three snippets
  the model called the security auditor on code whose only real problem was
  performance. That is a genuine limitation, not a rounding error. It is
  tolerable only because the errors are asymmetric: a missed performance audit
  costs an optimization suggestion, a missed security audit costs a
  vulnerability. It is measured rather than hidden, which is the point.
- **The backstop trades precision for safety, visibly.** It lifts performance
  recall to 67% but drops precision to 33% — it fires on anything with an
  auth/DB/exec keyword and pays for a performance audit that often finds
  nothing. That is the intended trade (a false positive costs cents), and now
  the cost is quantified rather than assumed.

The exit code fails when as-shipped security recall drops below 100%
(`--min-security-recall`), so a prompt or model change that quietly breaks
routing fails the way a test does.

> **Caveat, stated plainly:** these 20 cases were used to *tune* the tool
> docstrings (performance recall went 33% → 50% that way), so the numbers are
> optimistic — the set is not held out. A fresh set would score lower. To use
> this as a real regression gate, write new cases and do not tune against them.

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

- [Setup Guide](docs/SETUP.md) — git init, folder structure, and pushing to GitHub.
- [Technical Specification](docs/TECHNICAL_SPEC.md) — architecture, multi-agent graph topology, agent responsibilities, roadmap, and future phases.
- [Build & Deploy Guide](docs/BUILD_AND_DEPLOY.md) — what to prioritize for an interview showcase, build order, and deployment steps (Render/Railway + Cloudflare Pages).

## Roadmap

| # | Phase | State |
|---|---|---|
| 1 | **Local Code Review Studio** — LangGraph nodes, tool-calling supervisor, `/api/review`, React UI | ✅ done |
| 2 | **GitHub PR Bot** — webhook-triggered reviews posted as PR comments | ✅ done |
| 2a | Real GitHub repo/PR verification (token + webhook against a live PR) | next up |
| 2b | **Static analysis (Bandit) fused into `security_audit`** — findings from both engines merged into one list, tagged by source | ✅ done |
| 2c | Risk score on every review (severity + diff size, no new dependency) | planned |
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
