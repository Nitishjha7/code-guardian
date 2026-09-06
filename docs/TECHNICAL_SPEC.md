# Multi-Agent Autonomous Code Reviewer & PR Bot: Technical Specification & Implementation Guide

This document details the architectural blueprint, multi-agent orchestration model, safety constraints, and deployment guidelines for the Multi-Agent Autonomous Code Reviewer & PR Bot. Built using LangGraph, LangChain, Guardrails AI, Model Context Protocol (MCP), FastAPI, Docker, and React, this system automates multi-dimensional code auditing (security, performance, and code generation) with autonomous patch creation.

## 1. System Overview & Core Value Proposition

Manual peer code reviews are often slow and frequently miss subtle vulnerabilities like SQL injections, resource leaks, or performance degradation. A single generalist LLM prompt often lacks the domain-specific rigor required for deep auditing. The Multi-Agent Code Reviewer employs specialized agent personas coordinated via a centralized LangGraph Supervisor:

- **Specialized Agent Personas**: Independent auditing nodes for AppSec (OWASP, secret leaks) and Performance (Big-O, memory, caching).
- **Autonomous Remediation**: A Patch Generator Node synthesizes the findings of both auditors to produce actionable, production-ready code diffs.
- **Policy & Secrets Guardrails**: Guardrails AI guarantees that emitted code patches and comments do not expose environment variables, proprietary keys, or harmful configurations.
- **GitHub Integration**: Reads pull requests and posts review comments via PyGithub. *(This was originally specified as an MCP Server integration; it is not one — see §5 "Deviations". The model-driven tool calling this project does have lives in the supervisor, §3a.)*

## 2. Architecture & Multi-Agent Tech Stack

| Component | Technology | Role in System |
|---|---|---|
| Agent Orchestrator | LangGraph (StateGraph) | Multi-agent supervisor pattern — an LLM-driven **tool-calling router** (`bind_tools` + `ToolNode`) that selects specialists at runtime, with parallel execution, state reducers, and conditional edge routing. See §3a. |
| LLM Engine | LangChain + Groq (`openai/gpt-oss-120b` default, set via `GUARDIAN_MODEL`) | Inference engine powering the security, performance, and remediation agents. Groq retires model ids over time — check `/v1/models` before pinning one. |
| Safety & Guardrails | Guardrails AI (Secrets & Toxic Guards) | Scans output diffs to prevent API key leaks and validates tone of automated PR comments. |
| Tooling Layer | PyGithub (`app/mcp_clients/github_client.py`) | Fetches PR metadata and changed files, posts review comments. Implemented with PyGithub rather than the GitHub MCP server — see the note in [BUILD_AND_DEPLOY.md](BUILD_AND_DEPLOY.md); the model-driven tool calling in this project lives in the supervisor, not here. |
| Backend API | FastAPI (Asynchronous) | Provides webhook listener for GitHub PR events and REST endpoints for UI interaction. |
| Frontend Workspace | React + Tailwind CSS / Monaco Editor | Interactive code review dashboard displaying split diff views, security alerts, and agent logs. |
| Container Orchestration | Docker & Docker Compose | Containerized microservice stack ensuring reproducible local and cloud deployment. |

## 3. Multi-Agent State Machine & Graph Topology

The workflow employs a Supervisor/Fan-out architecture where Security and Performance audits run in parallel or sequentially, feeding their findings into a Patch Synthesizer before Guardrail validation.

```
                       +----------------------+
                       | User Code / PR Input |
                       +----------------------+
                                  |
                                  v
                       +----------------------+
                       |  Supervisor (LLM)    | <----------------+
                       |  bind_tools([...])   |                  |
                       +----------------------+                  |
                                  |                              |
                    [conditional: tool_calls?]                   |
                                  |                              |
                         yes      |      no ---------------+     |
                                  v                        |     |
                       +----------------------+            |     |
                       |       ToolNode       |            |     |
                       | (parallel execution) |            |     |
                       +----------------------+            |     |
                   +--------------+--------------+         |     |
                   |                             |         |     |
                   v                             v         |     |
        +--------------------+        +--------------------+     |
        |   security_audit   |        | performance_audit  |     |
        | (OWASP, Auth, PII) |        | (Big-O, Memory, DB)|     |
        +--------------------+        +--------------------+     |
                   |                             |         |     |
                   +--------------+--------------+         |     |
                                  |                        |     |
                       results appended to state ----------|-----+
                                                           |
                                  +------------------------+
                                  v
                       +----------------------+
                       | Patch Generator Node |
                       | (Produces Git Diff)  |
                       +----------------------+
                                  |
                                  v
                       +----------------------+
                       | Guardrail Validator  |
                       +----------------------+
                                  |
                                  v
                       +----------------------+
                       | Final Review & Patch |
                       +----------------------+
```

### 3a. Supervisor as a Tool-Calling Router (not a fixed fan-out)

The Supervisor is **not** a hard-coded "always run both auditors" step. It is an LLM bound to the specialist agents as **tools** (`llm.bind_tools([...])`), and it decides at runtime which specialists a given input actually needs.

```python
@tool
def security_audit(source_code: str, language: str) -> str:
    """Audit code for OWASP Top 10 issues, injection flaws, hardcoded secrets,
    insecure deserialization, and broken access control."""

@tool
def performance_audit(source_code: str, language: str) -> str:
    """Audit code for algorithmic complexity, N+1 queries, memory leaks,
    unclosed resources, and missing database indexes."""

supervisor_llm = llm.bind_tools([security_audit, performance_audit])
```

The Supervisor node emits tool calls; a `ToolNode` executes them (in parallel when more than one is requested) and appends results to state; a conditional edge routes back to the Supervisor until it stops calling tools, at which point control passes to the Patch Generator.

```
Supervisor --[tool_calls present]--> ToolNode --> Supervisor   (loop)
Supervisor --[no tool_calls]-------> Patch Generator
```

**Why this design over a static fan-out.** Three concrete reasons:

1. **Not every input needs every auditor.** A pure CSS diff has no meaningful security surface; a config-file change has no algorithmic complexity to analyze. A static fan-out pays for a full audit on every submission regardless — and with specialist prompts running over large diffs, that is the dominant cost in the system. Letting the model route makes the common case cheaper without any hand-written heuristic deciding which files are "security-relevant."
2. **The tool docstring *is* the routing logic.** Adding the Phase 3 agents (Code Quality, Test Coverage, Dependency/License, Documentation) becomes a matter of writing one more `@tool` with a clear docstring — no edge rewiring, no growing `if/elif` router. The graph topology stays constant as the agent roster grows, which is the entire point of a supervisor pattern.
3. **It demonstrates genuine tool calling.** The LLM selects a tool from a schema and produces structured arguments — the *model* driving control flow, as distinct from LangGraph *edges* driving it. Both patterns appear in this portfolio deliberately (see Positioning); knowing when each is appropriate is the actual skill.

**Trade-off, stated honestly:** the router can be wrong. A false negative — skipping the security audit on code that did have a vulnerability — is strictly worse than the wasted tokens a static fan-out would have spent. Three mitigations: `temperature=0` with docstrings written as routing *criteria* rather than prose descriptions; a forced-fan-out override flag on the API for high-stakes paths (any diff touching auth or database code); and an eval set of labelled snippets measuring routing **recall**, since a false negative is the only failure mode that really matters here.

**Why not `create_react_agent`?** The prebuilt ReAct agent handles this loop in one line, but it hides the state transitions — and the orchestration *is* the reviewable artifact of this project. The supervisor loop is wired explicitly for the same reason the Self-Healing SQL Agent avoids `SQLDatabaseChain`: the mechanism is the deliverable, not the feature.

### Multi-Agent State Schema Definition

```python
class ReviewerState(TypedDict):
    source_code: str               # Raw input code or pull request diff
    language: str                  # Python, JavaScript, SQL, Go, etc.
    security_issues: List[str]     # Findings from Security Agent
    performance_issues: List[str]  # Findings from Performance Agent
    fixed_code: str                # Remediation code generated by Patch Agent
    summary_report: str            # Final consolidated markdown review
    logs: List[str]                # Real-time state execution logs
```

## 4. Specialized Agent Responsibilities

| Agent Persona | Audit Focus & Rules | Expected Deliverable |
|---|---|---|
| Security Agent | OWASP Top 10, SQL Injection, hardcoded API secrets, unauthorized access, insecure deserialization. | Categorized vulnerability list with severity ratings (Critical, High, Medium). |
| Performance Agent | Unoptimized loops (O(n²) to O(n)), N+1 database queries, memory leaks, unclosed streams, missing indexes. | Optimization recommendations with Big-O complexity comparison. |
| Patch Generator | Synthesizes Security and Performance feedback without altering the original business logic. | Full refactored code block and unified git diff patch. |
| Supervisor / Router | Bound to the specialist agents as tools; decides at runtime which audits a given diff actually needs, loops until no further tool calls, then aggregates deliverables into GitHub PR Markdown and passes through Guardrails AI. | Routing decisions + production-ready markdown comment and sanitized code response. |

## 5. Implementation Status

Phases 1 and 2 are **implemented and verified against a live model**. Phases 3–5
remain roadmap (§7) by deliberate choice — see [BUILD_AND_DEPLOY.md](BUILD_AND_DEPLOY.md).

### Phase 1: Local Code Review Studio — ✅ done
- ✅ LangGraph graph with Security, Performance and Patch nodes (`app/graph.py`),
  supervisor wired as a tool-calling router with a `ToolNode` loop.
- ✅ FastAPI `/api/review`, plus `/api/health` and `/api/graph` (Mermaid topology).
- ✅ React + Monaco UI: findings / patch / markdown / agent-log tabs, per-auditor
  "not run" and "failed" states, force-full-audit override.
- ✅ Guardrails on every outbound diff, patch and comment.

### Phase 2: GitHub PR Bot — ✅ done
- ✅ `POST /webhook/github` with HMAC-SHA256 verification (`hmac.compare_digest`),
  **fails closed** when no secret is configured.
- ✅ Returns 202 and reviews in the background — GitHub abandons a delivery
  after 10s, and a real review takes longer.
- ✅ Reviews the lines a PR *adds*, aggregates per-file results into one comment.
- ⚠️ Implemented with **PyGithub, not the GitHub MCP server** — rationale in
  `app/mcp_clients/github_client.py` and [BUILD_AND_DEPLOY.md](BUILD_AND_DEPLOY.md).
  The model-driven tool calling in this project lives in the supervisor (§3a).
- ❌ Not exercised against a real repository; that needs a `GITHUB_TOKEN` and a
  live PR.

### Deviations from this spec, and why

| Spec said | Built instead | Why |
|---|---|---|
| Guardrails AI | Local pattern scanner, Guardrails AI optional | some hub validators pull a full torch install |
| Patch agent emits a git diff | Model emits the rewritten file; diff via `difflib` | LLM-authored unified diffs routinely fail to apply |
| GitHub MCP Server / PyGithub | PyGithub | MCP's value is *model-driven* tool choice; these calls are fixed and webhook-driven |
| `llama-3.3-70b-versatile` | `openai/gpt-oss-120b` | the former no longer exists on Groq |

### Measured routing quality

§3a's third mitigation — a labelled eval set — is implemented in `backend/evals/`
(20 cases). On `openai/gpt-oss-120b`: **security recall 100%** (zero false
negatives) both with and without the backstop; performance recall 50%
router-only, 67% as-shipped. The set was tuned against, so it is not held out.

## 6. Docker Deployment Configuration

The system is packaged with Docker Compose, providing seamless orchestration for both local code auditing and GitHub webhook ingestion.

- `docker-compose.yml` sets up the asynchronous FastAPI backend and React frontend served via Nginx reverse proxy.
- Nginx also proxies `/api/` to the backend container, so the browser needs no CORS preflight and the frontend ships with `VITE_API_URL=/api` in every environment.
- Environment variables are read from `backend/.env` at runtime: `GROQ_API_KEY` and `GUARDIAN_MODEL` (required), `GITHUB_TOKEN` and `GITHUB_WEBHOOK_SECRET` (Phase 2 only).
- The backend runs as a non-root user and is published on host port **8010** (container 8000), since 8000 is commonly occupied.
- Two auxiliary images exist for CI-style runs: `backend/Dockerfile.test` (unit tests, no key needed) and `backend/Dockerfile.eval` (routing eval, needs a key).

## 7. Future Phases

The original Phase 3–5 sketch (agent roster expansion, vector-DB memory,
full CI/CD auto-blocking) is kept below for reference, but the near-term
plan is the reality-checked list that follows it: additions that fit the
*existing* graph topology (§3a — "one more `@tool`, no edge rewiring") and
verified LLM behaviour, rather than a parallel research project.

### Near-term (fits current architecture, ordered by effort/impact)

1. ~~**Static analysis fused into `security_audit`**~~ — ✅ **done**
   (`app/agents/static_analysis.py`). Bandit runs as a subprocess inside the
   existing tool and its findings merge into the same `Finding` schema; no graph
   or schema change beyond one `source` field. Semgrep would slot in as one more
   `_run_*` function of the same shape.

   Measured on the vulnerable-Python demo: **8 raw findings deduplicate to 5**,
   of which **3 are confirmed by both engines** (`llm+bandit:B608`, `B324`,
   `B105`). Agreement escalates severity — the MD5 finding the LLM rated *High*
   became *Critical* once Bandit independently flagged it HIGH/HIGH — and Bandit
   contributed two SQL-injection sites the LLM had missed. That is the fusion
   argument holding up in practice, not in principle.

   Two implementation details worth knowing: Bandit's `code` field returns
   *numbered context lines*, so the offending line must be selected by
   `line_number` rather than taken first (doing the latter both misleads the
   reader and breaks dedup); and dedup matches by *containment* of the
   normalised line, because the LLM quotes an expression while the scanner
   reports the whole statement.
2. **Risk score** — a weighted score (`Finding` severities already sorted in
   `collect_node`, plus diff size) computed once, no new dependency. Turns the
   report from "here are some findings" into a single number a reviewer can
   triage on.
3. **Test Generation Agent** — a fourth `@tool` (`test_generation_audit`) that
   emits a regression test per finding (e.g. a `pytest` case asserting the SQL
   injection is blocked). Deliberately generation-only — no execution sandbox
   — because running LLM-authored code safely is a separate infrastructure
   problem, not a review-agent feature.
4. **GitHub Check Run status** — `pr_bot.py` already has a PyGithub client
   authenticated against the PR; publishing a Check Run (`success`/`failure`
   keyed off the risk score) is one more API call, and turns "posts a comment"
   into "can gate a merge" without touching the review graph at all.

### Deliberately deferred, and why

These come up often (RAG over the whole repo, a dependency/impact graph,
sandboxed patch validation, vector-DB team memory) and are *not* rejected on
merit — they're rejected because each is its own multi-week project (repo
ingestion, embeddings, a sandboxed execution runtime) rather than a node this
graph can absorb. Building them half-way would cost the "depth over breadth"
property this project is built on (see [BUILD_AND_DEPLOY.md](BUILD_AND_DEPLOY.md)).
They stay on the list as what Phase 3+ would need to become a
codebase-aware, self-healing agent, not as next sprint's work:

- **Phase 3: Advanced Intelligence Layer** — Code Quality, Dependency/License,
  and Documentation agents (Test Coverage is promoted above, since it fits
  the existing tool-calling pattern without new infra).
- **Phase 4: Learning & Memory** — a feedback loop and team-specific rules
  stored in a vector DB, historical PR pattern analysis. Requires persistent
  storage and embeddings the current stateless review graph doesn't have.
- **Phase 5: CI/CD Integration (full form)** — Slack/Discord notifications,
  auto-created Jira/Linear tickets. The Check Run gate above is the minimal,
  high-value slice of this phase; the rest is integration surface, not
  architecture.
- **Self-healing patch loop** (generate → apply → run tests → regenerate) and
  **codebase-wide dependency/impact graph** (AST/Tree-sitter parsing, "who
  calls this function") — both need multi-file repo context and, for the
  self-healing loop, a sandboxed execution environment. Out of scope until
  there's a concrete plan for both.
