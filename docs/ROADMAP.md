# Roadmap — kya ban chuka, kya bacha, aur kya jaan-boojh ke chhoda

Ye doc single source of truth hai status ka. README ka roadmap table isi ka summary
hai; [TECHNICAL_SPEC §7](TECHNICAL_SPEC.md) me deferred items ka detail hai.

---

## Current Status

| # | Phase | State |
|---|---|---|
| 1 | **Local Code Review Studio** — LangGraph nodes, tool-calling supervisor, `/api/review`, React UI | ✅ done |
| 2 | **GitHub PR Bot** — HMAC webhook, PyGithub client, PR comment | ✅ done |
| 2a | Real GitHub repo/PR verification | ⬜ **blocked on a token** |
| 2b | Static analysis (Bandit) fused into `security_audit` | ✅ done |
| 2c | Risk score on every review | ✅ done |
| 2d | Test Generation Agent | ✅ done |
| 2e | GitHub Check Run status (gate merges on risk score) | ⬜ next |
| 3–5 | Advanced Intelligence, Learning & Memory, full CI/CD | ⬜ deliberately deferred |

**Extra jo plan me nahi tha par ban gaya:** routing eval with a **held-out set**
(`backend/evals/`, 40 cases), 99 unit tests, aur poora docs set.

---

## Verified numbers

Jo bhi yahan likha hai wo actually chalaya gaya hai, claim nahi kiya gaya.

| Check | Result |
|---|---|
| Unit tests | **99 pass**, koi API key nahi |
| Routing eval, **held-out** (20 cases, never tuned) | as-shipped security recall **100%**, 0 false negatives; router-only 89%; performance 43% |
| Routing eval, dev (20 cases, tuned against) | as-shipped 100%; router-only 90%; performance 50% |
| Static fusion (vulnerable Python) | 8 raw → **5** dedup ke baad; **3 confirmed by both engines**; Bandit ne 2 SQLi extra pakde |
| Risk score | vuln Python **100/100 critical** · slow JS **10/100 low** · CSS **0/100 none** |
| Failed audit | band `unknown`, "score unavailable", "Audit failed — this code was not checked" |
| Test generation | 88 lines pytest, 3 findings ke liye |
| Router cost contrast | CSS **~0.9s** vs vuln Python **~11.4s** |
| Webhook auth | 202 · 401 · 401 · 503 |
| API errors | 503 · 502 · 429 |
| Frontend | production build clean |

**Jo verify nahi hua:** PR bot asli GitHub repo pe (token chahiye), aur agent prompts
ki quality kisi labelled dataset pe (sirf routing naapa hai, findings nahi).

---

## Bacha hua kaam

### 2a — Real GitHub verification ⬜ **blocked**

Chahiye: `GITHUB_TOKEN` (repo scope) + ek live PR.

GitHub API call tak sab tested hai — HMAC, event filtering, file selection, added-line
extraction. **PyGithub calls khud nahi.**

Steps [README](../README.md#github-pr-bot-phase-2) me hain. Webhook add karne ke baad
GitHub turant `ping` bhejta hai — Recent Deliveries me `202 {"status":"pong"}` dikhna
chahiye. Yahi sabse tez confirmation hai ki secret dono taraf match karta hai.

### 2e — GitHub Check Run ⬜ next

`pr_bot.py` me already authenticated PyGithub client hai, aur risk score already
compute hota hai. Ek aur API call chahiye:

```
conclusion = "failure"        if risk.band in ("high", "critical")
             "action_required" if not risk.complete
             "success"         otherwise
```

**`action_required` important hai:** incomplete review pe `success` khatarnak hai
(kisi ne dekha hi nahi) aur `failure` galat hai (pata hi nahi). "Insaan dekhe" hi sahi
jawab hai.

Isse "posts a comment" → "can gate a merge" ho jaata hai, review graph ko chhue bina.

---

## Deliberately deferred — aur kyun

Ye items **merit pe reject nahi hue**. Har ek apna multi-week project hai, ek node
nahi jise ye graph absorb kar sake. Aadha banane se wo "depth over breadth" property
chali jaati jispe ye project khada hai.

### Phase 3 — Advanced Intelligence Layer

Code Quality, Dependency/License, Documentation agents.

Ye technically aasan hain (har ek ek `@tool`), par **value per agent kam hai** aur
har naya agent routing precision girata hai. Test Coverage isliye upar promote hua
(2d) kyunki wo existing pattern me fit hota tha.

### Phase 4 — Learning & Memory

Feedback loop, team-specific rules (RAG), historical PR analysis.

Chahiye: persistent storage, embeddings, aur ek feedback capture mechanism. Abhi ka
review graph **stateless** hai — ye uska architecture change hai, addition nahi.

### Phase 5 — Full CI/CD Integration

Slack/Discord notifications, auto-created Jira/Linear tickets.

2e wala Check Run gate is phase ka **minimal, high-value slice** hai. Baaki integration
surface hai, architecture nahi — interview me wo kuch prove nahi karta.

### Self-healing patch loop

generate → apply → run tests → regenerate.

Chahiye: **sandboxed execution runtime** (no network, escape-proof filesystem, hard
timeout). Ye wahi wajah hai jisse 2d generation-only hai. Bina sahi sandbox ke ye tool
khud ek remote code execution ban jaata — ek *security* tool.

### Codebase-wide dependency/impact graph

"Is function ko kaun call karta hai" — AST/Tree-sitter parsing, multi-file context.

Isse cross-file vulnerabilities pakdi ja sakti hain jo abhi chhoot jaati hain (added
line + purani line ka interaction). Par repo ingestion apne aap me project hai.

---

## Known weaknesses — priority order me

Ye khud jaan-na interview me sabse zaroori hai:

1. **Performance routing kamzor hai** — dev set pe 50%, held-out pe 43%. Model
   performance-only code pe security auditor bula leta hai. Security ke ulta,
   yahan koi backstop nahi hai jo bachaye.
3. **Bandit sirf Python.** Baaki languages pe security audit akela LLM hai. Semgrep
   ek aur `_run_*` function hai — same shape, aur kuch nahi badalta.
4. **PR bot live verify nahi hua** (2a).
5. **Koi persistence nahi** — har review stateless.
6. **20 cases chhota sample hai** — 100% ka confidence interval chauda hai.

---

## Agar aur time mile — priority order

| # | Kaam | Effort | Kyun |
|---|---|---|---|
| 1 | **2a** — asli PR pe chalao | 30 min | "real automation" ka claim isi se sach hota hai |
| 2 | **2e** — Check Run gate | 1-2 hrs | comment → merge gate, risk score already hai |
| 3 | **Eval dobara 120b pe chalao** | 20 min | abhi ke numbers 20b se hain (120b ka quota khatam tha) |
| 4 | **Semgrep** multi-language | 2-3 hrs | Bandit-only limitation hatati hai |
| 5 | Findings quality eval (labelled vulns) | 1 day | abhi sirf routing naapa hai, findings nahi |
| 6 | Cost/token tracking | 3 hrs | abhi cost ka number bolne layak nahi hai |

**1 aur 2 interview se pehle karne layak hain.** 3 sabse imaandaar improvement hai.

---

## Deployment

Detail [BUILD_AND_DEPLOY.md](BUILD_AND_DEPLOY.md) me hai. Short version:

| Part | Platform |
|---|---|
| Backend (FastAPI + Docker) | Render / Railway |
| Frontend (React) | Cloudflare Pages / Vercel |

**Cloudflare Workers backend ke liye nahi chalega** — Python/FastAPI aur long-running
webhook process uske runtime me fit nahi hain.

Deploy karne se pehle: `GUARDIAN_MODEL` verify karo (Groq ids retire karta rehta hai),
`GITHUB_WEBHOOK_SECRET` set karo (warna webhook fail-closed 503 dega), aur
`GUARDIAN_CORS_ORIGINS` me deployed frontend ka URL daalo.
