# Code Guardian

**Multi-Agent Autonomous Code Reviewer & PR Bot**

Code Guardian is a multi-agent code auditing platform. It coordinates specialized LangGraph agents — Security, Performance, and Patch Generator — to review code or pull requests, flag vulnerabilities and inefficiencies, and autonomously generate production-ready fixes, all validated through Guardrails AI before being posted back as a GitHub PR review.

> ## Status: Phase 1 implemented, Phase 2 not started
>
> | Piece | State |
> |---|---|
> | Docs (README, spec, setup, build & deploy guide) | ✅ complete |
> | LangGraph graph, tool-calling supervisor, 3 agents, guardrails | ✅ implemented |
> | FastAPI `/api/review`, `/api/health`, `/api/graph` | ✅ implemented |
> | React + Monaco review dashboard | ✅ implemented |
> | Docker images + Compose stack | ✅ builds and runs |
> | Phase 2: GitHub webhook + MCP client (`app/mcp_clients/`) | ❌ not started |
>
> **What has actually been verified:** 21 backend unit tests pass; the frontend
> production build succeeds; both images build; the API serves `/api/health` and
> `/api/graph` (the compiled topology matches the spec), and correctly returns
> 503/502/429 when the LLM key is missing, rejected, or rate limited.
> **Not yet verified end-to-end:** a full review against a live Groq key — the
> agent prompts have not been run against the real model. Do that first
> (`Quick start` below) before demoing.

## Tech Stack

- **Agent Orchestrator**: LangGraph (StateGraph) — supervisor pattern built as an LLM **tool-calling router** (`bind_tools` + `ToolNode`): the model decides which specialists a given diff actually needs, instead of a fixed fan-out. Parallel tool execution, state reducers, conditional edge routing. See [§3a of the spec](docs/TECHNICAL_SPEC.md)
- **LLM Engine**: LangChain + Groq (Llama 3.3 70B / Claude / Gemini)
- **Safety & Guardrails**: Guardrails AI (secrets scanning, toxic-language guard)
- **Tooling Layer**: GitHub MCP Server / PyGithub (Model Context Protocol)
- **Backend**: FastAPI (async), webhook listener + REST API
- **Frontend**: React, Tailwind CSS, Monaco Editor
- **Deployment**: Docker & Docker Compose

## Project Structure

```
backend/app/graph.py           # LangGraph state machine (nodes + edges)
backend/app/state.py           # ReviewerState schema
backend/app/config.py          # Settings + shared LLM factory
backend/app/main.py            # FastAPI: /api/review, /api/health, /api/graph
backend/app/agents/            # Security, Performance, Patch Generator, Supervisor
backend/app/guardrails_config/ # Secrets + tone validators on all outbound text
backend/app/mcp_clients/       # GitHub / Filesystem MCP clients (Phase 2, empty)
backend/tests/                 # Unit tests for the LLM-free seams
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
- API: http://localhost:8000/api/health (interactive docs at `/docs`)

If port 8000 is taken on your machine, change the host side of the backend's
`ports:` mapping in `docker-compose.yml` (e.g. `"8010:8000"`); the frontend
reaches the backend over the compose network, so nothing else needs updating.

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
routing, the state collector, and the guardrails — so they run without an API
key or a single LLM call.

```bash
cd backend && pip install pytest && pytest -q
# or, with no local Python:
docker build -f backend/Dockerfile.test -t code-guardian-test backend && docker run --rm code-guardian-test
```

## Demo script

The UI ships three samples (top-left dropdown) chosen to make the router's
decision visible:

| Sample | Expected behaviour |
|---|---|
| Vulnerable Python (SQLi + N+1) | Both auditors run; Critical SQL injection, hardcoded password, MD5 password hashing, N+1 query loop; patch parameterizes the queries |
| Plain CSS | Router skips the security audit entirely — the "not run" state in the UI is the point |
| Slow JavaScript | Performance audit flags the O(n²) join and proposes a Map lookup |

The "Force full audit" checkbox is the §3a override: it bypasses routing and
runs every auditor, for high-stakes paths where a false negative is worse than
wasted tokens.

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
