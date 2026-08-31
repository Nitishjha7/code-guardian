# Build & Deploy Guide (Interview Project Focus)

Is document ka goal: Code Guardian ko interview-showcase project ke liye kaise banao (priorities), aur end me kaise deploy karo.

## Purpose

Main purpose: **interview me project dikhana**. Isliye depth + explainability zyada matter karti hai, breadth kam. Poora Phase 3-5 banane ki zaroorat nahi — sirf roadmap me likhe rehne se bhi kaam ban jaata hai.

## Kya banana hai (Priority Order)

### 1. Core (zaroor banao, well-polished)

- **LangGraph multi-agent graph** — Security Agent + Performance Agent + Patch Generator, properly connected via `StateGraph`. Ye interview ka sabse important part hai.
- **Tool-calling supervisor** — Supervisor ko fixed fan-out mat banao. Specialists ko `@tool` banao, `llm.bind_tools([...])` se supervisor ko bind karo, phir `ToolNode` + conditional edge se loop. **Ye is project ka sabse differentiating piece hai** — poore portfolio me yahi ek jagah hai jahan **LLM khud** control flow decide karta hai (baaki dono projects me LangGraph ke edges decide karte hain). "ReAct-style / tool calling banaya hai?" agentic AI interview ka common sawaal hai — iske bina jawab "nahi" hota hai. Detail + defence [TECHNICAL_SPEC.md §3a](TECHNICAL_SPEC.md) me hai.
- **FastAPI backend** — `/api/review` endpoint jo code accept kare aur graph trigger kare.
- **React UI** — simple code textarea/Monaco editor + "Review" button + result cards (security issues, performance issues, patch diff).
- **Guardrails AI integration** — output diffs/comments me secrets leak na ho, ye validate karo. Interview me "production-thinking" dikhata hai.
- **Clean architecture** — state schema (`ReviewerState`), node separation, docs (already ready in [SETUP.md](SETUP.md) & [TECHNICAL_SPEC.md](TECHNICAL_SPEC.md)).

### 2. Nice-to-have (agar time mile)

- **GitHub PR Bot (Phase 2)** — webhook listener jo PR open/update pe trigger ho, MCP/GitHub API se diff fetch kare, review comment post kare. Ye ek strong differentiator hai — "real automation", sirf toy demo nahi.

### 3. Skip for now (sirf README/roadmap me likho)

- Phase 3 (Code Quality, Test Coverage, Dependency/License, Documentation agents)
- Phase 4 (Feedback loop, vector DB memory, team-specific rules)
- Phase 5 (CI/CD auto-block, Slack/Discord alerts, auto-ticketing)

Ye sab already [TECHNICAL_SPEC.md](TECHNICAL_SPEC.md) ke "Future Phases" section me likhe hain — interviewer ko dikhega ki tumne aage ki soch rakhi hai, bina actually banaye.

## Interview me kaise present karo

- **"Kyun multi-agent (single LLM prompt kyun nahi)?"** — specialization/accuracy ka reasoning ready rakho: ek generalist prompt security aur performance dono deeply audit nahi kar pata, alag agents zyada focused/accurate hote hain.
- **"Supervisor har baar dono agents chalata hai?"** — Nahi. Supervisor ek tool-calling LLM hai; wo decide karta hai kis diff ko kaunsa audit chahiye. Pure CSS diff pe security surface hai hi nahi, config change me algorithmic complexity nahi hoti — static fan-out har submission pe poora cost deta hai. Aur naye agents add karna sirf ek naya `@tool` likhna hai, edges rewire karna nahi.
- **"Router galat decide kare toh?"** — Ye khud se bolo, ye maturity dikhata hai: false negative (security audit skip ho gaya jabki vulnerability thi) wasted tokens se kahin bura hai. Teen mitigation: `temperature=0` + docstrings ko routing *criteria* ki tarah likhna, high-stakes paths (auth/DB touch karne wale diffs) pe forced-fan-out override flag, aur labelled snippets ka eval set jo **recall** measure kare.
- **"ReAct-style tool calling banaya hai?"** — Haan, yahi wo project hai. Aur ye bhi bolo ki *kyun* sirf yahan: SQL agent me control flow deterministic hona chahiye (DB error se decide hota hai, model se nahi), yahan model ka judgement hi routing signal hai. Dono pattern jaante ho, aur kab kaunsa use karna hai wo bhi — yahi asli answer hai.
- Ek tricky design decision explain karne ke liye ready raho — jaise Guardrails kyun use kiya (secrets leak prevent karna), ya LangGraph state design kyun aisa rakha.
- **Live demo ready rakho**: vulnerable code paste karo (e.g. SQL injection wala snippet) → dikhao Security Agent flag karta hai → Patch Generator fix suggest karta hai. Phir CSS sample chalao — router dono auditors skip kar deta hai, ~0.9s vs ~6.4s. Ye contrast hi §3a ka poora argument hai, bolne se zyada asar karta hai.
- **"Agent fail ho jaye toh pata kaise chalega?"** — ye sawaal aa sakta hai, aur iska jawab tumhare paas actually code me hai: "did not run" aur "ran and found nothing" alag states hain (`failed_audits`), aur failed audit kabhi "No issues found" print nahi karta. Neeche implementation notes me detail hai.

### Groq model ids die — check before you demo

`llama-3.3-70b-versatile` (jo original spec me likha tha) ab Groq pe exist nahi karta; 404 deta hai. Demo se pehle ye chala lo:

```bash
curl https://api.groq.com/openai/v1/models -H "Authorization: Bearer $GROQ_API_KEY"
```

Jo id mile wahi `GUARDIAN_MODEL` me daalo. Abhi default `openai/gpt-oss-120b` hai (tool calling support karta hai, zaroori hai — supervisor isi pe chalta hai).

## Build Order (status)

1. ✅ `backend/app/graph.py` — LangGraph StateGraph + `ReviewerState` (in `state.py`)
2. ✅ `backend/app/agents/security_agent.py` + `performance_agent.py` — LLM calls with focused prompts
3. ✅ `backend/app/agents/patch_generator.py` — synthesize both findings into a diff
4. ✅ `backend/app/guardrails_config/` — secrets + tone guard on final output
5. ✅ FastAPI `/api/review` endpoint wiring the graph (`backend/app/main.py`)
6. ✅ React frontend — Monaco input + findings / patch / markdown / agent-log tabs
7. ❌ (Bonus) GitHub webhook + MCP client for PR automation — `app/mcp_clients/` is still empty

### Implementation notes worth knowing before the interview

Four places where the code deliberately departs from the naive reading of the
spec. Each is a decision you should be able to defend, not an accident:

- **A failed audit is never rendered as "no issues found".** This one is worth
  leading with, because it was a real bug caught during testing. The audits are
  tools, and LangGraph's `ToolNode` turns an uncaught exception into a plain
  ToolMessage — so when the Groq model id was retired and every audit 404'd, the
  system happily reported **0 findings on code with a Critical SQL injection**.
  For an auditing tool that is the worst possible failure: silence is
  indistinguishable from a pass. Fixed by having each tool return a
  `{"ok": bool, ...}` envelope, tracking `failed_audits` / `audit_errors` in
  state, and refusing to print "No issues found" for an audit that never ran —
  the report leads with an "incomplete review" banner instead. Four tests pin
  this behaviour down. Good interview answer to *"how do you know your agent
  actually worked?"*: you don't, unless you make "did not run" a distinct state
  from "ran and found nothing."

- **The diff is computed with `difflib`, not asked for from the LLM.** Models
  emit unified diffs with wrong hunk headers and line counts constantly, and
  such a patch will not apply. The model is asked only for the rewritten file;
  the diff is derived from the two texts, which is exact by construction.
- **Guardrails AI is an optional dependency; a local pattern scanner is the
  default.** Some `guardrails-ai` hub validators pull a full torch install — a
  bad trade for a container that otherwise fits in a few hundred MB. The
  fallback is written as a real guard (11 secret patterns, placeholder-aware so
  it does not flag the `os.environ[...]` the patch agent is *supposed* to emit),
  and `guardrail_report.engine` always names which engine produced the result.
  Do not claim "Guardrails AI" in an interview without saying this.
- **The router has a static backstop.** `looks_high_stakes()` in
  `supervisor.py` force-runs both auditors when the input obviously touches an
  auth, DB or exec surface, so the recall risk from §3a does not depend on the
  caller remembering to set `force_full_audit`. Deliberately over-inclusive: a
  false positive costs one extra audit, a false negative costs a vulnerability.

### What is tested

`backend/tests/` covers the LLM-free seams — JSON recovery from messy model
output, diff generation, the conditional-edge routing predicate, the state
collector (including a malformed tool result), and every guardrail pattern.
24 tests, no API key needed. There is **no** automated end-to-end test against a live
model; the agent prompts are unvalidated until you run a real review.

---

## Deployment

### Where to deploy

| Part | Platform | Why |
|---|---|---|
| Backend (FastAPI + Docker) | **Railway** or **Render** | Docker Compose deploys directly, free tier available |
| Frontend (React) | **Cloudflare Pages** or **Vercel** | Static build, free tier, fast global CDN |

**Cloudflare Workers backend ke liye nahi chalega** — Python/FastAPI aur long-running webhook process Workers runtime ke liye fit nahi hai. Cloudflare sirf frontend (Pages) ke liye use karo.

### Steps — Backend (Render example)

1. Repo ko GitHub pe push karo (already covered in [SETUP.md](SETUP.md)).
2. Render.com pe naya **Web Service** banao, GitHub repo connect karo.
3. Root directory: `backend/`
4. Build command: `pip install -r requirements.txt`
5. Start command: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
6. Environment variables set karo: `GROQ_API_KEY`, `GITHUB_TOKEN`, `DATABASE_URL` (agar DB use ho raha hai).
7. Deploy — Render automatically Docker/requirements detect kar lega.

### Steps — Frontend (Cloudflare Pages example)

1. Cloudflare dashboard → Pages → **Create a project** → GitHub repo connect karo.
2. Root directory: `frontend/`
3. Build command: `npm run build`
4. Output directory: `dist` (Vite) ya `build` (CRA)
5. Environment variable set karo: backend ka deployed URL (e.g. `VITE_API_URL=https://your-backend.onrender.com`)
6. Deploy — Cloudflare automatically HTTPS + CDN de dega.

### Steps — GitHub Webhook (agar Phase 2 bhi banaya)

1. GitHub repo settings → Webhooks → Add webhook.
2. Payload URL: deployed backend ka `/webhook/github` endpoint.
3. Content type: `application/json`
4. Events: "Pull requests" select karo.
5. Secret set karo aur backend me `GITHUB_WEBHOOK_SECRET` env var me daalo (signature verify karne ke liye).
