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
> | 50 backend unit tests | pass |
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
backend/app/guardrails_config/ # Secrets + tone validators on all outbound text
backend/app/pr_bot.py          # Phase 2: HMAC verification + PR review orchestration
backend/app/mcp_clients/       # GitHub client (PyGithub): PR diffs, comments
backend/tests/                 # 50 unit tests for the LLM-free seams
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
(HMAC verification, event filtering, file selection) — so they run without an
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
| Vulnerable Python (SQLi + N+1) | Both auditors run (the high-stakes backstop forces them). Critical SQL injection, High hardcoded password, Medium MD5 hashing; N+1 queries `O(n)` → `O(1)`, missing index, unclosed connection. 80-line patch. **~6.4s** |
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

Development is split into 2 core phases, with advanced phases beyond — see [docs/TECHNICAL_SPEC.md](docs/TECHNICAL_SPEC.md) for full details:

1. Local Code Review Studio — LangGraph nodes, FastAPI `/api/review` endpoint, React UI
2. GitHub PR Bot & MCP Integration — webhook-triggered reviews posted directly as PR comments
3. Advanced Intelligence Layer — Code Quality, Test Coverage, Dependency/License, Documentation agents
4. Learning & Memory — feedback loop, team-specific rules, historical PR analysis
5. CI/CD Integration — auto-block merge, chat notifications, auto-ticketing
