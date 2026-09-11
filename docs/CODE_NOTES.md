# Code Notes — Kya Kis Liye Hai

Har file ka **kyun**. Kya karti hai wo code padh ke dikh jaayega; ye doc wo batata
hai jo code padh ke nahi dikhta — kaunsa faisla liya gaya aur uske alternatives
kyun chhode.

Sawaal-jawab format me yahi cheezein [CODE_QA.md](CODE_QA.md) me hain. Poora system
kaise chalta hai — [PROJECT_WALKTHROUGH.md](PROJECT_WALKTHROUGH.md).

---

## backend/requirements.txt ✅

Teen cheezein dhyan dene layak:

- **`langgraph` + `langchain-groq`**, poora `langchain` nahi. Sirf `StateGraph`,
  `ToolNode` aur `ChatGroq` chahiye.
- **`bandit`** — ye ek *runtime* dependency hai, dev tool nahi. Wo `security_audit`
  ke andar chalti hai, CI me nahi.
- **`guardrails-ai` commented hai.** Uske kuch hub validators poora torch kheench
  lete hain. Container jo warna kuch sau MB ka hai, wo GB me chala jaata. Optional
  rakha, fallback asli guard banaya.

`typing-extensions>=4.12` explicit hai — wajah `state.py` me likhi hai.

---

## backend/app/config.py ✅

[config.py](../backend/app/config.py)

Do kaam: settings, aur **LLM factory ek hi jagah**.

`get_llm()` `lru_cache` ke saath hai, temperature ke hisaab se cached. Supervisor
aur auditors sab yahin se aate hain, taaki model/temperature/retry ek jagah badle.

**`temperature=0.0` default hai, aur ye deliberate hai.** Supervisor ka kaam
classification hai, creative writing nahi. Ek bhatakta router is project ka sabse
bura failure mode hai.

Key na ho to `RuntimeError` phenkta hai jisme **fix likha hota hai** (`cp .env.example`),
sirf "missing key" nahi. API use 503 me badal deta hai.

---

## backend/app/state.py ✅

[state.py](../backend/app/state.py)

Spec ka `ReviewerState` flat tha. Jo add hua:

| Field | Kyun |
|---|---|
| `messages` + `add_messages` reducer | supervisor tool-calling loop hai, use history chahiye |
| `force_full_audit` | §3a ka caller-side override |
| `failed_audits`, `audit_errors` | "chala hi nahi" aur "chala, kuch nahi mila" alag states |
| `risk` | ek baar compute, sab jagah wahi padha jaaye |
| `generated_tests`, `tests_note` | 2d ka output |
| `source` (Finding pe) | `llm`, `bandit:B608`, ya `llm+bandit:B608` |

### `TypedDict` `typing_extensions` se aata hai — ye ek asli bug tha

Python 3.11 pe **pydantic `typing.TypedDict` reject karta hai**. Graph compile hi
nahi hota. Error `build_graph()` pe aata hai, import ke aas-paas kahin nahi — isliye
dhoondhne me time laga.

---

## backend/app/agents/supervisor.py ✅ — **project ka differentiating piece**

[supervisor.py](../backend/app/agents/supervisor.py)

Poore portfolio me yahi ek jagah hai jahan **LLM khud control flow decide karta hai**.

### Tools ke arguments kyun nahi hain

[supervisor.py:41](../backend/app/agents/supervisor.py#L41)

`security_audit()` aur `performance_audit()` — dono zero-arg. Code unhe `ContextVar`
se milta hai.

Agar code tool argument hota, to model ko poora diff apne tool call me **wapas likhna**
padta. Wo input tokens do baar charge karta, aur bada diff model truncate kar sakta tha.

**`ContextVar`, plain module dict nahi** — API concurrent requests serve karta hai.
Global dict me do simultaneous reviews ek doosre ka code audit kar lete.

### Docstrings hi routing logic hain

[supervisor.py:69-107](../backend/app/agents/supervisor.py#L69-L107)

Dono docstrings *criteria* ki tarah likhi hain ("call this when the code does any of…"),
description ki tarah nahi. Naya agent add karna = ek aur `@tool` + clear docstring.
Edges rewire nahi hote.

Eval ne ye prove kiya: performance docstring ko criteria me badalne se recall
**33% → 50%** gaya. Sirf docstring badli.

### `_run_audit` ka envelope — silent-pass fix

[supervisor.py:50-66](../backend/app/agents/supervisor.py#L50-L66)

Har audit `{"ok": true, "findings": [...]}` ya `{"ok": false, "error": "..."}` deta hai.

Bare array se ye **batana hi possible nahi** ki "audit hua, kuch nahi mila" ya
"audit chala hi nahi". Ek code reviewer ke liye ye farak sab kuch hai.

### `looks_high_stakes` — backstop

[supervisor.py:134-158](../backend/app/agents/supervisor.py#L134-L158)

Jaan-boojh ke over-inclusive. False positive = ek extra audit. False negative =
chhoot gayi vulnerability.

**Bug jo yahin mila:** `\b` underscore aur letter ke beech fire nahi karta. Matlab
`\bpassword\b` `DB_PASSWORD` aur `check_password` dono miss karta hai — wahi naam jo
asli code me hote hain. Ab lookarounds hain. Yahi bug secrets guard me bhi tha.

Phrase-shaped patterns (`select … from`, `os.system`) alag regex me hain, kyunki unpe
wahi boundaries lag hi nahi sakti.

### `route_with_llm` alag kyun hai

[supervisor.py:172](../backend/app/agents/supervisor.py#L172)

Taaki eval **router ko akela** naap sake. Sirf shipped path naapte to backstop model
ki galtiyan chhupa deta aur number jhootha accha dikhta.

---

## backend/app/agents/security_agent.py ✅

[security_agent.py](../backend/app/agents/security_agent.py)

LLM call + Bandit, aur dono ka merge. Prompt me teen cheezein important hain:

- "Report only issues you can point to in the supplied code."
- "**An empty array is a valid and often correct answer; do not invent findings to
  seem thorough.**" — iske bina models har snippet pe kuch na kuch likh dete hain.
- Severity ki definition di hui hai (Critical = remotely exploitable), model ke
  apne paimane pe nahi chhoda.

Static analysis fail ho to wo **note** banta hai, exception nahi — LLM half succeed
kar chuka hota hai, aur usko ek optional dependency ki wajah se phenkna galat trade hai.

---

## backend/app/agents/performance_agent.py ✅

[performance_agent.py](../backend/app/agents/performance_agent.py)

Same shape. `complexity_before` / `complexity_after` isi ke findings pe hote hain.

Prompt me explicitly likha hai **"Do not report security issues; another agent owns
those."** — warna dono auditors ek hi cheez do baar report karte.

Ye project ka kamzor auditor hai: routing recall 50%. Detail [CODE_QA Q13](CODE_QA.md).

---

## backend/app/agents/static_analysis.py ✅ — LLM + Bandit fusion

[static_analysis.py](../backend/app/agents/static_analysis.py)

### Dono engines kyun, ek kyun nahi

- Bandit apne rule set pe **kabhi miss nahi karta**, aur jo rule nahi hai wo
  **hallucinate kar hi nahi sakta**.
- LLM wo pakadta hai jo kisi rule me likha nahi — missing authorization,
  business-logic flaw — aur context ke saath samjhata hai.

Koi ek doosre ko replace nahi karta. Isliye merge, aur `source` field se pata chalta
hai kisne kya diya.

### Severity matrix — do axes, ek rating

[static_analysis.py:41](../backend/app/agents/static_analysis.py#L41)

Bandit severity aur confidence alag deta hai. HIGH severity + LOW confidence ek
**lead** hai, Critical nahi. Matrix wahi collapse karta hai jaise ek reviewer karta.

### `_offending_line` — ek asli bug

[static_analysis.py:93](../backend/app/agents/static_analysis.py#L93)

Bandit ka `code` field aisa aata hai:

```
"2 \n3 DB_PASSWORD = \"hunter2\"\n4 \n"
```

Numbered **context** lines. Pehli line lene se padosi (aksar blank) line milti thi.
Do nuksaan: reader ko galat line dikhti, **aur dedup toot jaata** kyunki hint LLM ke
quote se match hi nahi karta.

### `_same_line` — containment, equality nahi

[static_analysis.py:212](../backend/app/agents/static_analysis.py#L212)

LLM expression quote karta hai (`hashlib.md5(...) == stored`), scanner poora statement
(`return hashlib.md5(...) == stored`). Equality maangte to har aisa pair do baar
report hota.

Length floor (12 chars) isliye hai ki `x = 1` sab kuch na nigal le.

### Agreement pe severity escalate hoti hai

[static_analysis.py:227](../backend/app/agents/static_analysis.py#L227)

Jispe do independent engines agree karte hain, wahi pehle padhna chahiye. Wording
LLM ki rehti hai (wo context samjhata hai), tag `llm+bandit:B608` ban jaata hai.

---

## backend/app/agents/patch_generator.py ✅

[patch_generator.py](../backend/app/agents/patch_generator.py)

**Diff `difflib` banata hai, LLM nahi.** Models unified diff me hunk headers aur line
counts galat dete hain, aur aisa patch apply hi nahi hota. Model se sirf rewritten
file maangi, diff do texts se derive — exact by construction, aur free.

Findings na ho to LLM call hi nahi hoti — no-op rewrite pe paisa nahi lagta.

Prompt me: business logic, public API, signatures preserve karo; jo safely fix nahi
ho sakta uspe `TODO(code-guardian):` comment; secret kabhi hardcode mat karo, env se
padho.

---

## backend/app/agents/test_generator.py ✅ (2d)

[test_generator.py](../backend/app/agents/test_generator.py)

### Kuch execute nahi hota — ye feature hai, kami nahi

LLM ke likhe tests safely chalane ke liye sandbox chahiye: no network, escape-proof
filesystem, hard timeout. Wo alag infrastructure project hai. Test likh ke dena jise
insaan padhe aur chalaye — imaandaar 80%. "Verify kar liya" bolna — khatarnak 20%.

Report me likha hai: *"generated, not executed"*.

### Node hai, `@tool` nahi — spec se deviation

Spec ne `@tool` likha tha. §3a ka apna argument hai ki model control flow tabhi
decide kare jab **judgement** chahiye. "Kaunsa audit is diff pe worth hai?" —
judgement. "Tests likhne layak findings hain kya?" — ek boolean, jo state me pehle
se hai. Router tool banate to model ko wo faisla dete jo ek `if` zyada sahi karta,
aur routing eval ka clean measurement bhi kharab hota.

### Performance findings ke tests kyun nahi

Benchmark ko threshold chahiye. LLM ke paas naapne ke liye machine nahi hai. Uska
chuna hua threshold flaky test banega — aur flaky test **no test se bura** hai,
kyunki team red ko ignore karna seekh jaati hai.

---

## backend/app/graph.py ✅ — orchestration

[graph.py](../backend/app/graph.py)

```
supervisor --[tool_calls]--> tools --> supervisor      (loop)
supervisor --[none]--------> collect --> patch --> guardrail --> END
                                            \--> tests --/
```

### `create_react_agent` kyun nahi

Wo ye loop ek line me kar deta, lekin state transitions chhupa deta. **Is project ka
reviewable artifact orchestration hi hai** — usko prebuilt ke peeche chhupana poora
point khatam kar deta.

### `_unpack_audit` — silent-pass ka doosra half

[graph.py:43-68](../backend/app/graph.py#L43-L68)

Jo parse na ho wo **error** hai, empty result nahi. `ToolNode` uncaught exception ko
plain-text ToolMessage bana deta hai; usko "no findings" padhna hi wo bug tha.

### `collect_node` me risk score kyun

[graph.py:108-116](../backend/app/graph.py#L108-L116)

Yahin findings pehli baar complete hoti hain. Ek jagah compute karke report, API, UI
aur PR comment sab wahi padhte hain — koi apna alag derive nahi karta.

### `_route_after_patch`

[graph.py:162](../backend/app/graph.py#L162)

Deterministic predicate, isliye edge me hai, model ke judgement me nahi.

### `_render_report` — failed audit kabhi "No issues found" nahi chhapta

[graph.py:204](../backend/app/graph.py#L204)

Section teen states jaanta hai: failed, not-run, aur genuinely-clean. Skim karne wala
reader galat natija na nikaale, isliye incomplete banner **sabse upar** aata hai.

### `guardrail_node` report render ke **baad** chalta hai

[graph.py:319](../backend/app/graph.py#L319)

Taaki model ne agar secret prose me copy kar diya ho to wo bhi pakda jaaye, sirf code
block ke andar wala nahi.

---

## backend/app/risk.py ✅ (2c)

[risk.py](../backend/app/risk.py)

### Weights bands ke against calibrated hain

[risk.py:37](../backend/app/risk.py#L37)

Ek Critical → *high*. Do → *critical*. Wajah: ek remotely exploitable vulnerability
merge rokne ke liye kaafi honi chahiye, jab Check Run gate ye number padhega.

Pehle `Critical = 40` tha aur band 50 se shuru hota tha — ek akela Critical *medium*
dikh raha tha. **Test ne ship hone se pehle pakad liya.**

### Teen properties

1. **Incomplete review kabhi safe nahi dikh sakta** — `band: "unknown"`, `0/none` nahi.
2. **Findings dominate** — size +25% pe capped, 2000-line clean diff phir bhi 0.
3. **Corroboration counts** — `llm+bandit` 1.25×; performance 0.4× (slow query ek
   cost hai, SQL injection ek breach).

PR level pe **worst file ka** score, average nahi — ek PR utna hi risky hai jitna
uska sabse khatarnak change.

---

## backend/app/guardrails_config/validators.py ✅ — custom, Guardrails AI **optional**

[validators.py](../backend/app/guardrails_config/validators.py)

11 secret patterns + 3 tone patterns. Diff, report aur patched code — teeno pe.

### Guardrails AI optional kyun hai

Uske kuch hub validators poora torch kheench lete hain. `guardrail_report.engine`
**hamesha** batata hai kaunsa engine chala. Interview me "Guardrails AI use kiya"
bolna hai to ye disclose karna zaroori hai.

### Redact karta hai, drop nahi

Reviewer ko patch ki shakal dikhni chahiye. Value `[REDACTED-BY-GUARDRAIL]` ban jaati
hai, poori line gayab nahi hoti.

### Placeholder-aware

`os.environ[...]`, `<your-api-key>`, `changeme` — ye wahi hain jo patch agent ko
**emit karne chahiye**. Inko flag karna guard ko bekaar bana deta.

### Tone guard me technical vocabulary excluded hai — asli false positive

Ek run me finding likhi thi *"relying on garbage collection"* — bilkul sahi technical
baat — aur guard ne use **insult** flag kar diya. Ab `garbage collection`,
`lazy loading/evaluation`, `dumb terminal`, `trash the cache` explicitly excluded hain.

Jo guard correct technical writing pe cry-wolf karta hai, wo guard log ignore karna
seekh jaate hain — yaani wo kuch bhi protect nahi karta.

---

## backend/app/main.py ✅

[main.py](../backend/app/main.py)

### Graph sync hai, isliye threadpool

[main.py:44](../backend/app/main.py#L44)

`anyio.CapacityLimiter(4)` — sync LangChain client event loop pe nahi chal sakta, aur
limiter Groq rate limit ke against concurrent reviews cap bhi karta hai.

### `Finding` schema fields ko string me coerce karta hai

[main.py:80-87](../backend/app/main.py#L80-L87)

Findings LLM se aati hain. Model `"line_hint": 42` de de to poora request fail nahi
hona chahiye.

### Error mapping

[main.py:150-168](../backend/app/main.py#L150-L168)

| Status | Kab |
|---|---|
| 503 | key set hi nahi |
| 502 | provider ne key reject ki |
| 429 | rate limit |
| 500 | baaki sab |

Rejected key ek **configuration problem** hai, review ka bug nahi — operator ko 500
aur raw provider payload dikhana galat hai.

---

## backend/app/pr_bot.py + mcp_clients/github_client.py ✅ (Phase 2)

[pr_bot.py](../backend/app/pr_bot.py) ·
[github_client.py](../backend/app/mcp_clients/github_client.py)

### Fail closed

[pr_bot.py:34](../backend/app/pr_bot.py#L34)

Secret configure nahi hai → **503, kuch process nahi hota**. Public URL jo LLM calls
chalata hai aur repos me likhta hai, wo denial-of-wallet vector hai. "Secret set karna
bhool gaya" kabhi "koi bhi bot chala sakta hai" nahi banna chahiye.

`hmac.compare_digest`, `==` nahi — plain comparison timing se correct prefix length
leak karta hai aur secret ek-ek byte guess ho jaata hai.

### 202 turant, review background me

GitHub 10s baad delivery abandon kar deta hai. Inline karte to har PR webhook log me
*failed delivery* dikhta.

### Sirf **added lines** review hoti hain

[github_client.py:144](../backend/app/mcp_clients/github_client.py#L144)

PR reviewer ka kaam naya code hai. Untouched context line pe pre-existing issue flag
karna wo noise hai jispe author is PR me kuch kar hi nahi sakta.

### File selection

10 files ka cap, **additions ke hisaab se ranked** — cap lage to trivia kate,
substance nahi. Lockfiles, minified, `node_modules/`, `vendor/`, migrations filtered.

**Bug yahan mila:** `/node_modules/` marker root-level `node_modules/x.js` se match
nahi karta tha, kyunki GitHub paths repo-relative hote hain (leading slash nahi). Ab
path normalize hota hai.

### "MCP" naam — imaandaar baat

Folder `mcp_clients/` hai, spec me "GitHub MCP Server / PyGithub" likha tha.
**Ye PyGithub hai.** MCP server chalane ka matlab ek aur (Node) container sirf un REST
calls ko wrap karne ke liye jo backend already karta hai. MCP ki asli value — *model*
runtime pe tools discover kare — yahan lagti hi nahi, kyunki ye calls fixed aur
webhook-driven hain.

**Interview me "MCP" bolo to `supervisor.py` ke baare me bolo, is file ke baare me nahi.**

---

## backend/evals/ ✅ — router ko naapne ke liye

[routing_cases.py](../backend/evals/routing_cases.py) ·
[run_routing_eval.py](../backend/evals/run_routing_eval.py)

20 labelled snippets. Label ka matlab: *"kya ek sane reviewer is audit ke paise dena
chahega"* — ye nahi ki auditor ko kuch milega hi.

### Do modes zaroori hain

- `router-only` — model ka judgement akela
- `as-shipped` — backstop ke saath, jo actually chalta hai

Sirf as-shipped dikhana model ko flatter karta; sirf router-only dikhana asli risk
overstate karta.

### Exit code gate hai

Security recall threshold se neeche → exit 1. Prompt ya model change jo routing chupke
se todta hai, wo test ki tarah fail hota hai.

**Recall gate hai, precision sirf report hoti hai** — errors symmetric nahi hain.

### Do sets — aur dusra kyun banana pada

`routing_cases.py` (dev) **tune karne me use hua** (performance recall 33% →
50%). Jis set pe tune kiya, uske numbers optimistic hote hain — wo measurement
nahi rehta.

Isliye `routing_cases_holdout.py`: 20 aise cases jinpe **kabhi tune nahi kiya**,
aur jaan-boojh ke mushkil —

- **alag languages** (Go, Java, SQL, shell) — docstrings Python/JS ke liye likhi thi
- **adversarial vocabulary** — no-audit cases jinme `token`, `auth`, `query`
  harmless jagah pe hain (`Token` dataclass, `author` field, `@media query`).
  Ye test karte hain ki model **code padh raha hai** ya sirf shabd match kar raha
  hai — kyunki backstop unhi shabdon pe chalta hai.
- **split cases** — security fix jo ek hot loop ke andar hai, cache jisme koi
  security surface nahi

**File ka niyam (uske docstring me likha hai):** agar case fail ho, to **na case
badlega na wo prompt** jispe wo fail hua. Jo held-out set score dekhne ke baad
edit ho jaaye, wo bas ek dheema dev set hai.

Result (`gpt-oss-20b`): as-shipped security recall dono set pe **100%**.
Router-only 89% holdout vs 90% dev — ek point ka gap, matlab tuning ne overfit
nahi kiya.

### `_MIN_COVERAGE` — eval ka apna silent-pass

Pehla version me errored cases **false negatives** me gin rahe the. Rate limit
lagi to eval ne "security recall 11%" chhaap diya — jo routing failure lagta hai
jabki wo infrastructure failure tha.

Ab errored cases score se **exclude** hote hain, aur 80% se kam cases chale to
**koi number chhapta hi nahi** — `INCONCLUSIVE`, exit 1. Wahi rule jo review
graph follow karta hai: jo run hua hi nahi, wo clean result nahi hai.

---

## backend/tests/ ✅ — 99 tests, koi API key nahi

Sab deterministic seams pe:

| File | Kya |
|---|---|
| `test_graph.py` | JSON recovery, diff, routing predicate, collector, failed audits |
| `test_guardrails.py` | secrets, placeholders, tone (+ technical vocabulary) |
| `test_static_analysis.py` | Bandit parse, severity matrix, line extraction, merge |
| `test_risk.py` | ordering properties, incomplete review, size cap |
| `test_pr_bot.py` | HMAC, event filtering, file selection, added-line extraction |
| `test_test_generator.py` | selection rule, routing predicate |

Jo **cover nahi** hai: agent prompts khud (sirf asli review se validate hote hain)
aur PyGithub calls (token + live PR chahiye).

---

## frontend/src/ ✅ — React + Vite + Tailwind + Monaco

[App.jsx](../frontend/src/App.jsx) · [components/](../frontend/src/components/) ·
[pages/](../frontend/src/pages/) · [lib/](../frontend/src/lib/)

Dashboard shell: sidebar nav, top bar, hero pipeline strip, review panel
(paste / GitHub PR / upload), agent finding cards, side-by-side patch, aur right
rail me system status + last review + recent activity.

### UI "AI-generated" na lage — iske liye kya hataya

Pehla version me hero banner tha, tagline tha, ek quote box ("Better Code, A
Safer Tomorrow"), sidebar me "AI Agents Working Together" wala promo card, aur
gradients. **Sab hata diya.**

Wajah: jis cheez me banda kaam karta hai, usme marketing copy filler lagti hai —
aur wahi sabse bada tell hoti hai ki UI generate kiya gaya hai, design nahi.
Linear, Vercel, GitHub — koi bhi tool apne hi dashboard pe apna tagline nahi
likhta.

Jo niyam lagaya: **jo decorate karne layak tha use delete kiya, style nahi
kiya.**

| Hataya | Kyun |
|---|---|
| Hero banner + tagline | tool me marketing copy |
| Quote box | pure decoration |
| Sidebar promo card | filler |
| 5 static pipeline chips | kabhi badalte nahi the |
| "Repository" page | kuch karta hi nahi tha |
| "Dashboard" page | "Code Review" ka duplicate tha |
| 7 unused icons | dead code |
| Gradients, blur | tool ko presentation deck bana rahe the |

Nav ab **5 items** hai, aur paanchon kuch karte hain. Health status ek badge me
aa gaya top bar me (`● openai/gpt-oss-120b`) — alag card ki zaroorat nahi thi.

### Routing library kyun nahi hai

Saat pages hain aur koi deep-linking requirement nahi. `useState` se page switch
karna ek dependency, ek bundle chunk aur ek build step bachata hai. Deep links
chahiye honge to react-router add karna seedha hai.

Icons bhi inline SVG hain ([Icons.jsx](../frontend/src/components/Icons.jsx)) —
paanch KB ke paths ek icon library se behtar hain.

### UI me jo dikhaya, wo isliye dikhaya

- **Risk donut + band + drivers** — ek hi number jo backend compute karta hai, UI
  apna alag derive nahi karta.
- **"not run" vs "failed"** alag dikhte hain. Ye poore project ka thesis hai; UI me
  chhupa dete to code me hone ka koi matlab nahi.
- **`confirmed` badge** (green ✓) jab dono engines ne ek hi line di.
- **Agent log tab** — har node ka faisla, timing ke saath. Demo me yahi dikhata hai
  ki router ne kya chuna.
- **Generated tests pe warning banner** — *"generated, not executed"*.

### `lib/history.js` — Recent Activity aur Analytics asli kyun hain

Backend stateless hai (persistence Phase 4 hai), to history `localStorage` me
rehti hai. Matlab har row ek review hai jo **actually chala** — placeholder nahi.

Trade-off chhupaya nahi: site data clear karne pe chali jaati hai, aur doosri
machine pe nahi jaati. Har read/write `try/catch` me hai kyunki private window aur
blocked storage dono throw karte hain.

### Jo jaan-boojh ke nahi dikhaya

- **Token count aur cost tile** — naapa nahi gaya. Usool: **jo number naapa nahi,
  wo dikhaya nahi jaata.**
- **Repository page** fake rows nahi dikhata — wo batata hai ki repo-wide review
  build hi nahi hui aur kyun.
- **Pull Requests page** token ke bina kaam nahi karta, aur wahi likha hai —
  "Connect GitHub" ka jhootha button nahi.

---

## Docker ✅

- `backend/Dockerfile` — non-root user, `$PORT` respect karta hai (Render/Railway)
- `backend/Dockerfile.test` — tests, key ki zaroorat nahi
- `backend/Dockerfile.eval` — routing eval, key chahiye
- `frontend/Dockerfile` — build + nginx
- `frontend/nginx.conf` — `/api/` proxy karta hai, isliye browser ko CORS preflight
  nahi chahiye aur frontend har environment me `VITE_API_URL=/api` ship karta hai
- `docker-compose.yml` — backend host port **8010** pe (8000 aksar busy hota hai)

---

## Aage jo bhi file banegi, uska explanation yahin niche add hoga.
