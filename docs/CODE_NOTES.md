# Code Notes — why each file exists

The **why** for every file. What the code does is visible by reading it; this
document holds what reading it does not show — which decision was made, and which
alternatives were rejected.

The same material in question-and-answer form is in [CODE_QA.md](CODE_QA.md). How
the whole system runs is in [PROJECT_WALKTHROUGH.md](PROJECT_WALKTHROUGH.md).

---

## backend/requirements.txt

Three things worth noticing:

- **`langgraph` + `langchain-groq`**, not the whole of `langchain`. Only
  `StateGraph`, `ToolNode` and `ChatGroq` are needed.
- **`bandit`** is a *runtime* dependency here, not a dev tool. It runs inside
  `security_audit`, not in CI.
- **`guardrails-ai` is commented out.** Some of its hub validators pull a full torch
  install, taking a container that otherwise fits in a few hundred MB into GB
  territory. It stays optional; the fallback was written as a real guard.

`typing-extensions>=4.12` is explicit — the reason is in `state.py`.

---

## backend/app/config.py

[config.py](../backend/app/config.py)

Two jobs: settings, and **a single place that builds the LLM**.

`get_llm()` is `lru_cache`d per temperature. Every agent goes through it, so the
model, temperature and retry policy change in one place.

**`temperature=0.0` is the default, deliberately.** The supervisor's job is
classification, not creative writing, and a wandering router is this system's worst
failure mode.

With no key it raises a `RuntimeError` that **contains the fix** (`cp .env.example`),
not just "missing key". The API turns that into a 503.

---

## backend/app/state.py

[state.py](../backend/app/state.py)

The spec's `ReviewerState` was flat. What was added:

| Field | Why |
|---|---|
| `messages` + `add_messages` reducer | the supervisor is a tool-calling loop and needs history |
| `force_full_audit` | the caller-side override from §3a |
| `failed_audits`, `audit_errors` | "never ran" and "ran, found nothing" are different states |
| `risk` | computed once, read everywhere |
| `generated_tests`, `tests_note` | output of roadmap item 2d |
| `source` (on `Finding`) | `llm`, `bandit:B608`, or `llm+bandit:B608` |

### `TypedDict` comes from `typing_extensions` — this was a real bug

On Python 3.11, **pydantic rejects `typing.TypedDict`**, and the graph will not
compile at all. The error surfaces at `build_graph()`, nowhere near the import, which
is why it took a while to find.

---

## backend/app/agents/supervisor.py — the differentiating piece

[supervisor.py](../backend/app/agents/supervisor.py)

The one place in the portfolio where **the model decides control flow**.

### Why the tools take no arguments

[supervisor.py:41](../backend/app/agents/supervisor.py#L41)

`security_audit()` and `performance_audit()` are both zero-arg; the code reaches them
through a `ContextVar`.

If the code were a tool argument, the model would have to **write the whole diff back
out** in its call. Those input tokens are charged twice, and a large diff risks being
truncated — leaving the auditor with half the code and no way to know.

**A `ContextVar`, not a module dict**: the API serves concurrent requests, and a
global would let two simultaneous reviews audit each other's code.

### The docstrings are the routing logic

[supervisor.py:69-107](../backend/app/agents/supervisor.py#L69-L107)

Both are written as *criteria* ("call this when the code does any of…"), not
descriptions. Adding an agent is one more `@tool` with a clear docstring; no edges
are rewired.

The eval proved this: rewriting the performance docstring in criteria form moved
recall **33% → 50%**. Only the docstring changed.

### The `_run_audit` envelope — the silent-pass fix

[supervisor.py:50-66](../backend/app/agents/supervisor.py#L50-L66)

Every audit returns `{"ok": true, "findings": [...]}` or
`{"ok": false, "error": "..."}`.

A bare array **cannot express** the difference between "audited, found nothing" and
"never ran". For a code reviewer that difference is everything.

### `looks_high_stakes` — the backstop

[supervisor.py:134-158](../backend/app/agents/supervisor.py#L134-L158)

Deliberately over-inclusive. A false positive costs one extra audit; a false negative
costs a vulnerability.

**The bug found here:** `\b` does not fire between an underscore and a letter, so
`\bpassword\b` misses both `DB_PASSWORD` and `check_password` — exactly the names real
code uses. It now uses lookarounds. The same bug was sitting in the secrets guard.

Phrase-shaped patterns (`select … from`, `os.system`) live in a separate regex,
because those boundaries cannot apply to them.

### Why `route_with_llm` is separate

[supervisor.py:172](../backend/app/agents/supervisor.py#L172)

So the eval can measure **the router alone**. Measuring only the shipped path would
let the backstop hide the model's mistakes and produce a falsely good number.

---

## backend/app/agents/security_agent.py

[security_agent.py](../backend/app/agents/security_agent.py)

An LLM call plus Bandit, merged. Three things in the prompt matter:

- "Report only issues you can point to in the supplied code."
- "**An empty array is a valid and often correct answer; do not invent findings to
  seem thorough.**" Without this, models write something on every snippet.
- Severity is defined for the model (Critical = remotely exploitable) rather than
  left to its own scale.

If static analysis fails it becomes a **note**, not an exception — the LLM half has
already succeeded, and throwing that away over an optional dependency is the wrong
trade.

---

## backend/app/agents/performance_agent.py

[performance_agent.py](../backend/app/agents/performance_agent.py)

Same shape. `complexity_before` / `complexity_after` belong to its findings.

The prompt says explicitly **"Do not report security issues; another agent owns
those"** — otherwise both auditors report the same thing twice.

This is the project's weaker auditor: routing recall 50% dev, 43% held-out. Details
in [CODE_QA Q32](CODE_QA.md).

---

## backend/app/agents/static_analysis.py — LLM + Bandit fusion

[static_analysis.py](../backend/app/agents/static_analysis.py)

### Why both engines, not one

- **Bandit** cannot miss a pattern it has a rule for, and cannot **hallucinate** one
  it does not.
- **The LLM** catches what no rule encodes — missing authorization, business-logic
  flaws — and explains it in context.

Neither replaces the other. Hence the merge, and the `source` field so a reader can
see which engine produced which line.

### The severity matrix — two axes, one rating

[static_analysis.py:41](../backend/app/agents/static_analysis.py#L41)

Bandit reports severity and confidence separately. HIGH severity at LOW confidence is
a **lead**, not a Critical. The matrix collapses them the way a reviewer would.

### `_offending_line` — a real bug

[static_analysis.py:93](../backend/app/agents/static_analysis.py#L93)

Bandit's `code` field looks like this:

```
"2 \n3 DB_PASSWORD = \"hunter2\"\n4 \n"
```

Numbered **context** lines. Taking the first gave a neighbouring, often blank, line.
Two harms: the reader saw the wrong line, **and dedup broke silently**, because the
hint no longer matched the LLM's quote of the real one.

### `_same_line` — containment, not equality

[static_analysis.py:212](../backend/app/agents/static_analysis.py#L212)

The LLM quotes an expression (`hashlib.md5(...) == stored`); the scanner reports the
whole statement (`return hashlib.md5(...) == stored`). Requiring equality would report
every such pair twice.

The 12-character floor stops `x = 1` from swallowing everything.

### Agreement escalates severity

[static_analysis.py:227](../backend/app/agents/static_analysis.py#L227)

A finding two independent engines agree on should be read first. The LLM's wording
survives (it explains the context) and the tag becomes `llm+bandit:B608`.

---

## backend/app/agents/patch_generator.py

[patch_generator.py](../backend/app/agents/patch_generator.py)

**The diff is computed by `difflib`, not by the LLM.** Models emit unified diffs with
wrong hunk headers and line counts, and such a patch will not apply. The model returns
only the rewritten file; the diff is derived from the two texts — exact by
construction, and free.

With no findings, no LLM call is made at all — no money is spent on a no-op rewrite.

The prompt requires: preserve business logic, public API and signatures; mark anything
unfixable with a `TODO(code-guardian):` comment; never hardcode a secret, read it from
the environment.

---

## backend/app/agents/test_generator.py (roadmap 2d)

[test_generator.py](../backend/app/agents/test_generator.py)

### Nothing is executed — that is a feature, not a gap

Safely running LLM-authored tests needs a sandbox: no network, an escape-proof
filesystem, a hard timeout. That is a separate infrastructure project. Writing a test
a human reads and runs is the honest 80%; claiming "I verified it" is the dangerous
20%.

The report says so literally: *"generated, not executed"*.

### A node, not a `@tool` — a deviation from the spec

The spec said `@tool`. But §3a's own argument is that the model should decide control
flow only where **judgement** is needed. "Which audit is this diff worth?" is
judgement. "Are there findings worth testing?" is a boolean already in state — an
`if` gets it right more often, and a third router tool would also pollute the routing
eval.

### Why performance findings get no tests

A benchmark needs a threshold, and the LLM has no machine to measure on. Its guess
produces a flaky test — and a flaky test is **worse than no test**, because it trains
the team to ignore red.

---

## backend/app/graph.py — orchestration

[graph.py](../backend/app/graph.py)

```
supervisor --[tool_calls]--> tools --> supervisor      (loop)
supervisor --[none]--------> collect --> patch --> guardrail --> END
                                            \--> tests --/
```

### Why not `create_react_agent`

It would do this loop in one line, but it hides the state transitions. **The
orchestration is this project's reviewable artifact** — hiding it behind a prebuilt
defeats the point.

### `_unpack_audit` — the other half of the silent-pass fix

[graph.py:43-68](../backend/app/graph.py#L43-L68)

Anything that fails to parse is an **error**, not an empty result. `ToolNode` turns an
uncaught exception into a plain-text ToolMessage, and reading that as "no findings"
*was* the bug.

### Why the risk score is computed in `collect_node`

[graph.py:108](../backend/app/graph.py#L108)

This is where the findings are first complete. Computing it once means the report, the
API, the UI and the PR comment all read the same number instead of each deriving its
own.

### `_route_after_patch`

[graph.py:162](../backend/app/graph.py#L162)

A deterministic predicate, so it lives in an edge rather than in a model's judgement.

### `_render_report` never prints "No issues found" for a failed audit

[graph.py:204](../backend/app/graph.py#L204)

Each section knows three states: failed, not-run, and genuinely clean. The incomplete
banner leads the report so a skimming reader cannot draw the wrong conclusion.

### `guardrail_node` runs *after* the report is rendered

[graph.py:319](../backend/app/graph.py#L319)

So that a secret the model copied into prose is caught too, not only one inside a code
block.

---

## backend/app/risk.py (roadmap 2c)

[risk.py](../backend/app/risk.py)

### The weights are calibrated against the bands

[risk.py:37](../backend/app/risk.py#L37)

One Critical → *high*. Two → *critical*. The requirement: a single remotely
exploitable vulnerability must be enough to stop a merge when the Check Run gate reads
this number.

The first version used `Critical = 40` against a band starting at 50, so a lone
Critical scored as *medium*. **A test caught it before it shipped.**

### Three properties

1. **An incomplete review can never look safe** — band `unknown`, not `0/none`.
2. **Findings dominate** — size is capped at +25%, so a 2000-line clean diff still
   scores 0.
3. **Corroboration counts** — `llm+bandit` findings weigh 1.25×; performance findings
   are discounted to 0.4× (a slow query is a cost, a SQL injection is a breach).

Across a PR the **worst file's** score is used, not an average — a PR is exactly as
risky as its most dangerous change.

---

## backend/app/guardrails_config/validators.py — custom, Guardrails AI optional

[validators.py](../backend/app/guardrails_config/validators.py)

11 secret patterns plus 3 tone patterns, applied to the diff, the report and the
patched code.

### Why Guardrails AI is optional

Some of its hub validators pull a full torch install.
`guardrail_report.engine` **always** names which engine ran. If you want to say
"Guardrails AI" in an interview, this has to be disclosed with it.

### It redacts rather than drops

The reviewer needs to see the **shape** of the patch. The value becomes
`[REDACTED-BY-GUARDRAIL]`; the line does not vanish.

### It is placeholder-aware

`os.environ[...]`, `<your-api-key>`, `changeme` — these are exactly what the patch
agent is **supposed to emit**. Flagging them would make the guard useless.

### Technical vocabulary is excluded from the tone guard — a real false positive

In one run a finding read *"relying on garbage collection"* — perfectly correct
technical writing — and the guard flagged it as an insult. `garbage collection`,
`lazy loading/evaluation`, `dumb terminal` and `trash the cache` are now excluded
explicitly.

**A guard that cries wolf on correct technical writing is one people learn to
ignore — and then it protects nothing.**

---

## backend/app/main.py

[main.py](../backend/app/main.py)

### The graph is synchronous, so it runs in a thread

[main.py:44](../backend/app/main.py#L44)

`anyio.CapacityLimiter(4)` — the sync LangChain client must not run on the event loop,
and the limiter also caps concurrent reviews against the Groq rate limit.

### The `Finding` schema coerces fields to strings

[main.py:80-87](../backend/app/main.py#L80-L87)

Findings come from an LLM. A model returning `"line_hint": 42` should not fail the
whole request.

### Error mapping

| Status | When |
|---|---|
| 503 | no key configured |
| 502 | the provider rejected the key |
| 429 | rate limited |
| 500 | everything else |

A rejected key is a **configuration problem**, not a bug in the review — showing an
operator a 500 and a raw provider payload would be wrong.

### `/api/review-pr` reads but never writes

It returns the comment it *would* post, for preview. Reading a PR and commenting on it
are different levels of consequence, and only the webhook should do the second.

---

## backend/app/pr_bot.py + mcp_clients/github_client.py (Phase 2)

[pr_bot.py](../backend/app/pr_bot.py) ·
[github_client.py](../backend/app/mcp_clients/github_client.py)

### Fail closed

[pr_bot.py:34](../backend/app/pr_bot.py#L34)

No secret configured → **503, nothing processed**. A public URL that runs LLM calls
and writes into repositories is a denial-of-wallet vector. "I forgot to set the
secret" must never become "anyone can drive this bot".

`hmac.compare_digest`, not `==` — a plain comparison leaks the correct prefix length
through timing, and the secret can be guessed a byte at a time.

### 202 immediately, review in the background

GitHub abandons a delivery after 10 seconds. Working inline would make every
non-trivial PR show as a failed delivery — and GitHub disables webhooks after repeated
failures.

### Only added lines are reviewed

[github_client.py:144](../backend/app/mcp_clients/github_client.py#L144)

A PR reviewer's job is the **new code**. Flagging a pre-existing issue on an untouched
context line is noise the author cannot act on in this PR — and exactly what trains
people to ignore bots.

### File selection

A 10-file cap, **ranked by additions** so the cap drops trivia rather than substance.
Lockfiles, minified bundles, `node_modules/`, `vendor/` and migrations are filtered.

**The bug found here:** the `/node_modules/` marker did not match a root-level
`node_modules/x.js`, because GitHub paths are repo-relative and carry no leading
slash. Paths are now normalised.

### The "MCP" name — stated honestly

The folder is `mcp_clients/` and the spec said "GitHub MCP Server / PyGithub".
**This is PyGithub.** Running the MCP server would mean a second (Node) container
wrapping REST calls this backend already makes, and MCP's real value — a *model*
discovering and calling tools at runtime — does not apply, because these calls are
fixed and webhook-driven.

**If you say "MCP" in an interview, say it about `supervisor.py`, not this file.**

---

## backend/evals/ — measuring the router

[routing_cases.py](../backend/evals/routing_cases.py) ·
[routing_cases_holdout.py](../backend/evals/routing_cases_holdout.py) ·
[run_routing_eval.py](../backend/evals/run_routing_eval.py)

Labelled snippets. A label means *"would a sane reviewer pay for this audit"* — not
*"will the auditor find something"*.

### Two sets, and why the second was necessary

`routing_cases.py` (dev) was **used for tuning** (performance recall 33% → 50%). A set
you tune against stops being a measurement — it becomes training signal.

Hence `routing_cases_holdout.py`: 20 cases **never tuned against**, deliberately
harder —

- **different languages** (Go, Java, SQL, shell); the docstrings were written for
  Python and JS
- **adversarial vocabulary** — no-audit cases containing `token`, `auth`, `query` in
  harmless positions (a `Token` dataclass, an `author` field, an `@media query`).
  These test whether the model is **reading the code** or matching words, because the
  backstop keys off exactly those words.
- **split cases** — a security fix inside a hot loop; a cache with no security surface

**The file's rule, written in its own docstring:** if a case fails, **neither the case
nor the prompt it failed on may change.** A held-out set you edit after seeing the
score is just a slower dev set.

Result (`gpt-oss-20b`): as-shipped security recall **100% on both sets**. Router-only
89% held-out against 90% dev — a one-point gap, so the tuning did not overfit.

### Two modes are necessary

- `router-only` — the model's judgement alone
- `as-shipped` — with the backstop, i.e. what actually runs

Reporting only as-shipped flatters the model; reporting only router-only overstates
the real risk.

### The exit code is a gate

Below the security-recall threshold → exit 1. When the held-out set ran, the gate
reads *its* number, because that is the only uncontaminated one. A prompt or model
change that quietly breaks routing fails like a test.

**Recall gates; precision is only reported** — the errors are not symmetric.

### `_MIN_COVERAGE` — the eval's own silent pass

The first version counted errored cases as **false negatives**. When a rate limit hit,
the eval printed "security recall 11%" — which looks like a routing failure but was an
infrastructure failure.

Errored cases are now **excluded** from scoring, and below 80% coverage **no number is
printed at all** — `INCONCLUSIVE`, exit 1. The same rule the review graph follows: a
run that did not happen is not a clean result.

---

## backend/tests/ — 107 tests, no API key

All on deterministic seams:

| File | Covers |
|---|---|
| `test_graph.py` | JSON recovery, diff, routing predicate, collector, failed audits |
| `test_guardrails.py` | secrets, placeholders, tone (including technical vocabulary) |
| `test_static_analysis.py` | Bandit parsing, severity matrix, line extraction, merge |
| `test_risk.py` | ordering properties, incomplete reviews, the size cap |
| `test_pr_bot.py` | HMAC, event filtering, file selection, PR-link parsing |
| `test_test_generator.py` | the selection rule and the routing predicate |

**Not covered:** the agent prompts themselves (only a real review validates those) and
the PyGithub calls (they need a token and a live PR).

---

## frontend/src/ — React + Vite + Tailwind + Monaco

[App.jsx](../frontend/src/App.jsx) · [components/](../frontend/src/components/) ·
[pages/](../frontend/src/pages/) · [lib/](../frontend/src/lib/)

A dashboard shell: sidebar nav, top bar, review panel (code / pull request / upload),
a run strip, per-agent finding cards, a side-by-side patch, and a right rail with the
last review and recent activity.

### Making it not look generated

The first version had a hero banner, a tagline, a quote box ("Better Code, A Safer
Tomorrow"), an "AI Agents Working Together" promo card in the sidebar, and gradients.
**All removed.**

Reason: in something people are meant to work in, marketing copy reads as filler — and
it is the clearest tell that a UI was generated rather than designed. Linear, Vercel
and GitHub do not put their own tagline inside their own dashboard.

The rule applied: **anything that would have been decorated was deleted instead.**

| Removed | Why |
|---|---|
| Hero banner + tagline | marketing copy inside a tool |
| Quote box | pure decoration |
| Sidebar promo card | filler |
| Five static pipeline chips | never changed |
| "Repository" page | did nothing |
| "Dashboard" page | duplicated "Code Review" |
| Seven unused icons | dead code |
| Gradients, blur | made a tool look like a slide deck |

Five nav items remain and all five do something. Health moved into a top-bar badge
(`● openai/gpt-oss-120b`); it did not need a card.

### `RunStrip` — the demo centrepiece

Shows what the last run actually did, stage by stage. On a CSS file both auditors read
*skipped*; on vulnerable Python they read *ran*. The routing decision made visible
rather than described.

### Why there is no router library

Five pages and no deep-linking requirement, so page state lives in the **URL hash**
(`lib/router.js`). That gives refresh-safety and a working back button without a
dependency.

Hash rather than `history.pushState` because the app is served as static files behind
nginx — real paths would 404 on reload unless every route were rewritten to
`index.html`.

Icons are inline SVG ([Icons.jsx](../frontend/src/components/Icons.jsx)) — a few
kilobytes of paths beat an icon library.

### What the UI shows, and why

- **Risk donut, band and drivers** — the number the backend computed; the UI never
  derives its own.
- **"not run" versus "failed"** are visibly different. That is the project's whole
  thesis; hiding it in the UI would make its presence in the code pointless.
- **`confirmed` badge** where both engines flagged the same line.
- **Agent log tab** — every node's decision with timing. This is what shows the
  router's choice during a demo.
- **A warning banner on generated tests** — *"generated, not executed"*.

### `lib/history.js` — why Recent Activity and History are real

The backend is stateless (persistence is Phase 4), so history lives in
`localStorage`. Every row is therefore a review that **actually ran** — not a
placeholder.

The trade-off is stated rather than hidden: clearing site data wipes it, and it does
not follow you to another machine. Every read and write is wrapped in `try/catch`,
because private windows and blocked storage both throw.

### What is deliberately not shown

- **No token/cost tile** — it has not been measured. The rule: **anything not
  measured is not displayed.**
- **The Pull Requests page** says it needs `GITHUB_TOKEN` rather than rendering
  placeholder rows.
- **The Repository page was removed** — repo-wide review is not built, and a nav item
  that leads nowhere is worse than a missing one.

---

## Docker

- `backend/Dockerfile` — non-root user, respects `$PORT` (Render/Railway)
- `backend/Dockerfile.test` — tests, no key required
- `backend/Dockerfile.eval` — routing eval, key required
- `frontend/Dockerfile` — build + nginx
- `frontend/nginx.conf` — proxies `/api/`, so the browser needs no CORS preflight and
  the frontend ships with `VITE_API_URL=/api` in every environment
- `docker-compose.yml` — backend on host port **8010** (8000 is commonly taken)

---

## Any file added later gets its explanation here.
