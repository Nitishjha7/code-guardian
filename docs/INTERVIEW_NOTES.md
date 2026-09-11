# Code Guardian — Complete Interview Prep

Ye doc pitch, architecture, trade-offs, limitations aur Q&A ek jagah rakhta hai.
Code-level sawaal [CODE_QA.md](CODE_QA.md) me hain; general concepts
[AGENT_FUNDAMENTALS.md](AGENT_FUNDAMENTALS.md) me.

---

## Table of Contents

1. [The 30-second pitch](#1-the-30-second-pitch)
2. [The problem](#2-the-problem)
3. [Is this real or a portfolio toy?](#3-is-this-real-or-a-portfolio-toy)
4. [What the system actually does](#4-what-the-system-actually-does)
5. [Architecture](#5-architecture)
6. [Core USPs](#6-core-usps)
7. [Design trade-offs](#7-design-trade-offs)
8. [Limitations & mitigations](#8-limitations--mitigations)
9. [How to present it](#9-how-to-present-it)
10. [Anticipated questions](#10-anticipated-questions)
11. [Positioning alongside the other projects](#11-positioning-alongside-the-other-projects)
12. [Demo strategy](#12-demo-strategy)
13. [Resume one-liner](#13-resume-one-liner)
14. [Honesty checklist — what NOT to claim](#14-honesty-checklist--what-not-to-claim)
15. [An honest assessment of how strong this is](#15-an-honest-assessment)

---

## 1. The 30-second pitch

> Code Guardian ek multi-agent code reviewer hai. Ek LLM supervisor decide karta hai
> ki diye hue diff pe kaunse specialist auditors chalane chahiye — security,
> performance, dono, ya koi nahi. Security auditor ke andar Bandit bhi chalta hai,
> to har finding pe pata hota hai ki wo LLM ne di, scanner ne di, ya dono ne
> independently. Findings ek risk score me badalti hain, ek patch me, aur ek
> regression test me. Aur ek audit agar fail ho jaaye, system **kabhi** "no issues
> found" nahi bolta — wo poore review ko incomplete mark karta hai.
>
> Router ko naapa bhi hai: 20 labelled cases pe security recall 100%, zero false
> negatives.

Teen cheezein isme jaan-boojh ke hain: **model control flow decide karta hai**,
**deterministic scanner LLM ke saath fused hai**, aur **failure silence se alag hai**.

---

## 2. The problem

Manual code review slow hai aur subtle cheezein miss karta hai — SQL injection,
resource leak, N+1 query.

Lekin asli sawaal ye hai: **"LLM se review karwa lo" wala naive solution kyun kaafi
nahi?** Teen wajah:

| Problem | Naive prompt | Yahan |
|---|---|---|
| Ek generalist prompt security aur performance dono deeply audit nahi karta | ek hi prompt, shallow dono jagah | alag personas, focused criteria |
| Har submission pe poora cost | CSS file pe bhi full security analysis | router decide karta hai, CSS pe ~0.9s |
| LLM chup ho gaya — miss kiya ya chala hi nahi? | pata hi nahi chalta | `failed_audits` alag state |
| LLM hallucinate kar sakta hai | koi second opinion nahi | Bandit fused, `confirmed` tag |

---

## 3. Is this real or a portfolio toy?

Imaandaar jawab: **ye ek working system hai jise production me chalane se pehle kaam
chahiye.**

Kya asli hai:
- Docker stack chalti hai, dono entry points (UI + webhook) live verify hue
- 99 unit tests, koi API key ke bina
- Router ka recall **naapa** hua hai, assume nahi
- Paanch bugs asli runs se mile (neeche §8)

Kya nahi hai:
- PR bot asli repo pe kabhi nahi chala (token chahiye)
- Ek hi language ka static scanner (Bandit = Python only)
- Koi persistence nahi — har review stateless hai
- Eval set held-out nahi hai

Ye distinction khud bolna interviewer pe achha impression daalta hai. "Production-ready"
bolna aur phir pakde jaana sabse bura outcome hai.

---

## 4. What the system actually does

```
code / PR diff
   → high-stakes check (auth/DB/exec keywords?) → forced fan-out
   → warna supervisor LLM routes (bind_tools, temperature 0)
   → ToolNode parallel execution
        security_audit  = LLM + Bandit, merged, dedup by line
        performance_audit = Big-O, N+1, leaks, unclosed resources
   → collect: ok/error envelope unpack, severity sort, risk score
   → patch: model rewrites file, difflib computes diff
   → tests (only if Critical/High security): regression test per finding
   → guardrail: 11 secret patterns + tone, redact not drop
   → report + patch + tests + risk + full agent log
```

---

## 5. Architecture

| Component | Tech | Role |
|---|---|---|
| Orchestrator | LangGraph `StateGraph` | supervisor loop, conditional edges, reducers |
| Router | `llm.bind_tools()` + `ToolNode` | model picks auditors at runtime |
| LLM | Groq `openai/gpt-oss-120b` | tool calling required |
| Scanner | Bandit (subprocess) | deterministic rules, fused into security audit |
| Scoring | `risk.py` | one triage number, corroboration-aware |
| Safety | custom validators (Guardrails AI optional) | secrets + tone on outbound text |
| API | FastAPI | `/api/review`, `/api/health`, `/api/graph`, `/webhook/github` |
| PR bot | PyGithub | HMAC-verified webhook, reviews added lines |
| UI | React + Vite + Tailwind + Monaco | findings, patch, markdown, agent log |

---

## 6. Core USPs

### 6.1 Tool-calling supervisor — the differentiating piece

Poore portfolio me yahi ek jagah hai jahan **LLM khud control flow decide karta hai**
(baaki projects me LangGraph ke edges decide karte hain).

Naya agent = ek aur `@tool` + clear docstring. Graph topology same. **Docstring hi
routing logic hai** — aur ye prove hua: performance docstring ko criteria ki tarah
rewrite karne se recall 33% → 50% gaya, bina koi edge chhue.

### 6.2 Measured routing, not asserted

20 labelled snippets, do modes. **Security recall 100%, zero false negatives.**
Exit code threshold se neeche fail karta hai, to prompt/model change jo routing chupke
se tode wo test ki tarah pakda jaata hai.

### 6.3 LLM + deterministic scanner fusion

Scanner apne rules pe miss nahi karta aur hallucinate nahi kar sakta; LLM wo pakadta
hai jo kisi rule me nahi. `llm+bandit:B608` tag = dono ne independently dekha, aur
severity escalate hoti hai.

### 6.4 Failure is never silence

`failed_audits` / `audit_errors` alag states. Failed audit pe report "incomplete"
banner deti hai aur risk score `unknown` band, `0/none` nahi.

### 6.5 Risk score calibrated against a gate

Ek Critical → *high* band, do → *critical*, kyunki ek remotely exploitable
vulnerability merge rokne ke liye kaafi honi chahiye.

### 6.6 Fail-closed webhook

Secret na ho → 503. `hmac.compare_digest`. 202 + background (GitHub 10s pe abandon
karta hai).

---

## 7. Design trade-offs

| Faisla | Kya chhoda | Kyun |
|---|---|---|
| Router, static fan-out nahi | guaranteed coverage | cost + extensibility; backstop se recall bachaya |
| `difflib` se diff, LLM se nahi | "AI ne diff banaya" | LLM diffs apply hi nahi hote |
| Bandit fused, standalone nahi | simplicity | ek hi list reviewer padhta hai |
| Tests generate, execute nahi | "self-healing" claim | sandbox alag project hai |
| PyGithub, MCP server nahi | "MCP integration" buzzword | MCP ki value model-driven choice me hai; ye calls fixed hain |
| Custom guardrails, Guardrails AI optional | library ka naam | torch dependency container ko GB me le jaati |
| Added lines only (PR) | cross-line vulnerabilities | author untouched line pe kuch kar nahi sakta |

---

## 8. Limitations & mitigations

### L1 — Router ka false negative

Sabse bada risk. **Mitigation:** temperature 0, criteria-style docstrings,
`looks_high_stakes` backstop, `force_full_audit` flag, aur recall eval jo gate karta hai.
**Naapa:** security recall 100% dono modes me.

### L2 — Performance routing weak hai (50%)

Teen snippets pe model ne performance-only code pe security auditor bulaya.
**Mitigation:** koi nahi, abhi. **Tolerable kyunki** errors asymmetric hain, aur ab ye
naapa hua hai.

### L3 — Bandit sirf Python

Baaki languages pe security audit akela LLM hai. **Mitigation:** report me `source`
field dikhta hai, to reviewer ko pata hota hai. Semgrep add karna ek aur `_run_*`
function hai, aur kuch nahi badalta.

### L4 — Eval set held-out nahi hai

Isi pe tune kiya (33% → 50%). **Numbers optimistic hain.** README me likha hai.
Real gate ke liye naye cases chahiye jinpe tune na kiya ho.

### L5 — Generated tests kabhi chale nahi

Jaan-boojh ke. Report me "generated, not executed" likha hai.

### L6 — Koi memory nahi

Har review stateless hai. Agar developer suggestion reject kare, system yaad nahi
rakhta. Phase 4 hai, aur wo vector DB + persistence maangta hai.

### L7 — PR bot asli repo pe verify nahi hua

GitHub API call tak sab tested hai; PyGithub calls khud nahi.

---

## 9. How to present it

**Structure (3 min):**

1. **Problem** (20s) — naive "LLM se review karwa lo" kyun kaafi nahi (§2 ki table)
2. **Architecture** (40s) — supervisor routes, auditors parallel, patch + tests,
   guardrail
3. **Live demo** (90s) — §12
4. **The bug story** (30s) — silent clean pass. Isse close karo, ye yaad rehta hai.

**Jo lead karna hai:** *"main tumhe ek bug dikhata hoon jo maine khud is system me
pakda"* — technical depth ka sabse tez proof.

---

## 10. Anticipated questions

### Technical

**Q. "Multi-agent kyun? Ek prompt kaafi nahi tha?"**
Ek generalist prompt security aur performance dono deeply audit nahi karta. Alag
personas ke paas focused criteria hote hain. Aur separation se router possible hota
hai — jo cost bachata hai.

**Q. "ReAct-style tool calling banaya hai?"**
Haan, yahi wo project hai. Aur *kyun sirf yahan* bhi bolo: SQL agent me control flow
deterministic hona chahiye (DB error decide karta hai, model nahi); yahan model ka
judgement hi routing signal hai. **Dono pattern jaante ho aur kab kaunsa — yahi asli
jawab hai.**

**Q. "`create_react_agent` use kyun nahi kiya? Ek line me ho jaata."**
Wo state transitions chhupa deta. Is project ka reviewable artifact orchestration hi
hai — usko prebuilt ke peeche chhupana poora point khatam kar deta.

**Q. "LLM hallucinate kare to?"**
`security_audit` ke andar Bandit bhi chalta hai. Scanner apne rules pe miss nahi karta
aur hallucinate kar hi nahi sakta. Har finding pe `source` hota hai. Jo dono ne di,
wo `llm+bandit:B608` aur severity escalated.

**Q. "Tumhe kaise pata agent actually chala?"**
(Ye sabse achha sawaal hai — §7 CODE_QA ka pura jawab yahan aata hai.) Short version:
pata nahi chalta, jab tak "did not run" ko "ran and found nothing" se alag state na
banao. Aur ye ek asli bug tha.

**Q. "State design aisa kyun?"**
`messages` reducer ke saath (supervisor loop ko history chahiye), findings alag lists
(alag consumers), `failed_audits` alag (silent-pass), `risk` ek jagah compute.

**Q. "Scale kaise karoge? 200-file PR?"**
Abhi 10 files ka cap hai, additions ke hisaab se ranked. Aage: per-file parallelism,
aur file-level caching by content hash — same file dobara PR me aaye to re-review na ho.

**Q. "Cost kya hai per review?"**
Naapa nahi hai, aur isliye **number nahi bolunga**. Jo structurally pata hai: router
ek chhota call hai, auditors bade; CSS pe zero auditor calls hoti hain. Cost dashboard
roadmap me hai.

### Product

**Q. "Ye CodeRabbit/Snyk se better kaise hai?"**
Better nahi — ye unke architecture ka ek imaandaar demonstration hai. Jo differentiator
dikhane layak hai: routing ka cost control, LLM+scanner fusion with provenance, aur
failure ko silence se alag rakhna. Ye teeno commercial tools me aksar transparent nahi
hote.

**Q. "Team isko trust kyun karegi?"**
Teen wajah: har finding pe source dikhta hai; incomplete review khud ko incomplete
bolti hai; aur risk score calibrated hai, isliye gate predictable hai.

---

## 11. Positioning alongside the other projects

Teen projects hain: **Adaptive CRAG**, **Self-Healing SQL Agent**, **Code Guardian**.

### "Ye teeno ek hi project nahi hain?"

Nahi, aur farak **control flow kaun decide karta hai** pe hai:

| Project | Control flow kaun decide karta hai | Kyun |
|---|---|---|
| Adaptive CRAG | LangGraph edges, ek LLM grader ke verdict pe | grading judgement hai, routing deterministic |
| Self-Healing SQL | DB ka error message | error deterministic signal hai, model ka opinion nahi chahiye |
| **Code Guardian** | **LLM khud, tool calling se** | "is diff pe kaunsa audit worth hai" judgement hai |

Yahi teeno ko ek saath strong banata hai: **tum jaante ho kab model ko control dena
hai aur kab nahi.** Ye ek pattern ko teen baar dohrana nahi hai.

### Kisse lead karna hai

- **Agentic/LLM-orchestration role** → Code Guardian (tool calling + eval)
- **RAG role** → Adaptive CRAG
- **Data/backend role** → Self-Healing SQL

---

## 12. Demo strategy

Teen scenario, isi order me. Poora ~2 minute.

### Scenario 1 — Vulnerable Python (the money shot)

Dropdown se "Vulnerable Python" → Review.

Dikhane layak:
- **Risk 100/100 critical** — banner sabse upar
- **3 findings pe `confirmed` badge** — dono engines
- **2 SQLi sites jo sirf Bandit ne pakde**
- Patch tab → unified diff
- **Agent log tab** → "routing bypassed — high-stakes heuristic"

### Scenario 2 — Plain CSS (the architecture shot)

Same flow, CSS sample.

**~0.9s vs ~11.4s.** Dono sections "not run" dikhte hain.

> *"Router ne decide kiya ki CSS pe security surface hai hi nahi. Static fan-out
> yahan bhi poora paisa kharch karta."*

Ye contrast bolne se zyada asar karta hai.

### Scenario 3 — The failure (if time)

`GUARDIAN_MODEL` ko bakwaas id pe set karke re-run.

> *"Ye wo bug tha jo maine pakda. Pehle ye '0 findings' bolta tha — us code pe jisme
> Critical SQL injection tha. Ab poora review incomplete mark hota hai."*

**Demo se pehle:**
```bash
curl https://api.groq.com/openai/v1/models -H "Authorization: Bearer $GROQ_API_KEY"
```
Groq model ids retire karta rehta hai. Ek baar phas chuke ho.

---

## 13. Resume one-liner

> **Code Guardian** — Multi-agent code reviewer (LangGraph + Groq) jisme ek LLM
> supervisor `bind_tools` se runtime pe specialist auditors choose karta hai; Bandit
> static analysis LLM findings ke saath fused with provenance tagging; risk scoring,
> autonomous patch + regression-test generation, aur HMAC-verified GitHub PR bot.
> Routing quality 20 labelled cases pe naapi gayi — **security recall 100%**.

---

## 14. Honesty checklist — what NOT to claim

| ❌ Mat bolo | ✅ Bolo |
|---|---|
| "Guardrails AI use kiya" | "Custom validators; Guardrails AI optional hai, aur engine report me naam aata hai" |
| "MCP integration hai" | "PyGithub hai. Model-driven tool calling supervisor me hai" |
| "Self-healing hai" | "Tests generate hote hain, execute nahi — sandbox alag project hai" |
| "Production me chal raha hai" | "Working system hai; PR bot asli repo pe verify nahi hua" |
| "Router 100% accurate hai" | "Security recall 100% on 20 cases, jinpe tune bhi kiya — held-out nahi" |
| "Performance audit strong hai" | "Routing recall 50% — yahi weak spot hai" |
| "Cost X% kam karta hai" | "CSS pe 0.9s vs 11.4s; per-review cost naapa nahi" |

**Usool:** jo naapa nahi gaya, wo number nahi banta.

---

## 15. An honest assessment

### Iski strength architecture nahi hai

Supervisor pattern, LangGraph, tool calling — ye sab documented patterns hain. Koi
interviewer inse impress nahi hoga.

**Iski strength ye hai ki system apne failure modes ke baare me imaandaar hai**, aur
wo imaandaari code me enforced hai:

- Ek failed audit *chup* nahi reh sakta — schema level pe
- Ek incomplete review *safe* nahi dikh sakta — risk score level pe
- Ek finding ka source *chhupaya* nahi ja sakta — `Finding` schema level pe
- Router ki quality *claim* nahi ki ja sakti — eval gate karta hai

Ye engineering judgement hai, library knowledge nahi. Aur yahi wo cheez hai jo
portfolio projects me aksar nahi hoti.

### Weaknesses — poochhe jaane se pehle jaan lo

1. **Eval set held-out nahi hai.** Sabse pakde jaane layak baat.
2. **Performance routing 50%** hai.
3. **Bandit sirf Python** — multi-language claim kamzor hai.
4. **PR bot live verify nahi hua.**
5. **Koi persistence/memory nahi** — har review stateless.
6. **20 cases chhota sample hai** — 100% ka interval chauda hai.

Inme se har ek pe tumhare paas ya mitigation hai ya "jaan-boojh ke deferred" ka reason.
Jo nahi hai, wo maan lo — wahi sabse achha jawab hai.
