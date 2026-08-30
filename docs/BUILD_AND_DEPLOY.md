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
- **Live demo ready rakho**: vulnerable code paste karo (e.g. SQL injection wala snippet) → dikhao Security Agent flag karta hai → Patch Generator fix suggest karta hai.

## Build Order (suggested)

1. `backend/app/graph.py` — LangGraph StateGraph + `ReviewerState` schema
2. `backend/app/agents/security_agent.py` + `performance_agent.py` — LLM calls with focused prompts
3. `backend/app/agents/patch_generator.py` — synthesize both findings into a diff
4. `backend/app/guardrails_config/` — secrets + toxicity guard on final output
5. FastAPI `/api/review` endpoint wiring the graph
6. React frontend — code input + result display
7. (Bonus) GitHub webhook + MCP client for PR automation

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
