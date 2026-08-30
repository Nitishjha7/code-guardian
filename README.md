# Code Guardian

**Multi-Agent Autonomous Code Reviewer & PR Bot**

Code Guardian is a multi-agent code auditing platform. It coordinates specialized LangGraph agents — Security, Performance, and Patch Generator — to review code or pull requests, flag vulnerabilities and inefficiencies, and autonomously generate production-ready fixes, all validated through Guardrails AI before being posted back as a GitHub PR review.

> ## ⚠️ Status: design complete, implementation not started
>
> Every file under `backend/app/` is currently an empty scaffold. This README and
> the technical spec describe the **intended** system — they are a design
> document, not a description of running code.
>
> | Piece | State |
> |---|---|
> | Docs (README, spec, setup, build & deploy guide) | ✅ complete |
> | Repo scaffold, `docker-compose.yml` | ✅ complete |
> | LangGraph agents, tool-calling supervisor, FastAPI, frontend | ❌ not written |
>
> Build order is in [docs/BUILD_AND_DEPLOY.md](docs/BUILD_AND_DEPLOY.md). Until
> Phase 1 lands, do not present this as a working project — describe it as designed
> and in progress.

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
backend/app/agents/           # Security, Performance & Patch Generator agents
backend/app/mcp_clients/      # GitHub / Filesystem MCP clients
backend/app/guardrails_config/# Guardrails AI validators
backend/app/graph.py          # LangGraph state machine
frontend/src/                 # React review dashboard
docs/                         # Setup & technical spec docs
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
