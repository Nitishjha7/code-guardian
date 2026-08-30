# Multi-Agent Autonomous Code Reviewer & PR Bot: Technical Specification & Implementation Guide

This document details the architectural blueprint, multi-agent orchestration model, safety constraints, and deployment guidelines for the Multi-Agent Autonomous Code Reviewer & PR Bot. Built using LangGraph, LangChain, Guardrails AI, Model Context Protocol (MCP), FastAPI, Docker, and React, this system automates multi-dimensional code auditing (security, performance, and code generation) with autonomous patch creation.

## 1. System Overview & Core Value Proposition

Manual peer code reviews are often slow and frequently miss subtle vulnerabilities like SQL injections, resource leaks, or performance degradation. A single generalist LLM prompt often lacks the domain-specific rigor required for deep auditing. The Multi-Agent Code Reviewer employs specialized agent personas coordinated via a centralized LangGraph Supervisor:

- **Specialized Agent Personas**: Independent auditing nodes for AppSec (OWASP, secret leaks) and Performance (Big-O, memory, caching).
- **Autonomous Remediation**: A Patch Generator Node synthesizes the findings of both auditors to produce actionable, production-ready code diffs.
- **Policy & Secrets Guardrails**: Guardrails AI guarantees that emitted code patches and comments do not expose environment variables, proprietary keys, or harmful configurations.
- **MCP Integration**: Integrates GitHub MCP Server and Filesystem MCP Server to read pull requests and inspect repository trees natively.

## 2. Architecture & Multi-Agent Tech Stack

| Component | Technology | Role in System |
|---|---|---|
| Agent Orchestrator | LangGraph (StateGraph) | Multi-agent supervisor pattern — an LLM-driven **tool-calling router** (`bind_tools` + `ToolNode`) that selects specialists at runtime, with parallel execution, state reducers, and conditional edge routing. See §3a. |
| LLM Engine | LangChain + Groq (Llama 3.3 70B / Claude / Gemini) | Inference engine powering specialized security, performance, and remediation agents. |
| Safety & Guardrails | Guardrails AI (Secrets & Toxic Guards) | Scans output diffs to prevent API key leaks and validates tone of automated PR comments. |
| Tooling Layer (MCP) | GitHub MCP Server / PyGithub | Model Context Protocol client fetching PR metadata, changed files, and posting review comments. |
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

## 5. Implementation Roadmap: 2-Phase Strategy

### Phase 1: Local Code Review Studio (1-2 Days)
- Set up LangGraph graph with Security, Performance, and Patch nodes.
- Create FastAPI `/api/review` endpoint.
- Build React UI with code textarea, syntax highlighting, and collapsible audit cards.

### Phase 2: GitHub PR Bot & MCP Integration (Bonus / Advanced)
- Connect GitHub MCP Server or GitHub Webhook listener.
- Automatically trigger analysis when a Pull Request is opened or updated.
- Post formatted reviews and patch suggestions directly as PR review comments.

## 6. Docker Deployment Configuration

The system is packaged with Docker Compose, providing seamless orchestration for both local code auditing and GitHub webhook ingestion.

- `docker-compose.yml` sets up the asynchronous FastAPI backend and React frontend served via Nginx reverse proxy.
- Environment variables (`GROQ_API_KEY`, `GITHUB_TOKEN`) are injected dynamically at runtime.

## 7. Future Phases

### Phase 3: Advanced Intelligence Layer
- **Code Quality Agent** — naya agent jo readability, naming conventions, DRY principle check kare.
- **Test Coverage Agent** — dekh le ki naya code test cases ke saath hai ya nahi, aur khud test cases generate kar de.
- **Dependency/License Agent** — check kare ki naye packages mein koi vulnerable ya risky license wali library toh nahi aa rahi (jaise npm audit ka AI version).
- **Documentation Agent** — automatically docstrings/comments generate kare jo missing hain.

### Phase 4: Learning & Memory
- **Feedback Loop** — agar developer ne AI ka suggestion reject kiya, system yaad rakhe (vector DB mein store karke) taaki agli baar wahi galti na kare.
- **Team-specific rules** — har team ka apna coding style guide ho, us hisaab se review customize ho (RAG use karke).
- **Historical PR analysis** — purane bugs ka data dekh ke pattern samjhe ki is codebase mein kaunsi galtiyan baar baar hoti hain.

### Phase 5: CI/CD Integration
- **Auto-block merge** — agar Critical security issue mile toh PR ko merge hone se rok de (GitHub branch protection ke saath).
- **Slack/Discord notifications** — jab review complete ho ya critical issue mile, team ko turant alert bheje.
- **Auto-create Jira/Linear ticket** — agar bada issue mile toh khud hi ticket bana de.

### Extra Cool Features
- **Multi-language support** — abhi Python/JS wagera hai, isme Rust, Go, Java bhi add kar sakte ho.
- **Voice/Chat interface** — developer chat mein bot se poochh sake "ye function kyun flag hua?"
- **Diff visualization** — Monaco editor mein side-by-side before/after with inline explanations.
- **Cost/token tracking dashboard** — kitna LLM cost lag raha hai per review, wo track kare.
