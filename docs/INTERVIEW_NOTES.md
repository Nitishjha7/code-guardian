# Interview Preparation

Pitch, architecture, trade-offs, limitations and Q&A in one place. Code-level
questions live in [CODE_QA.md](CODE_QA.md); general concepts in
[AGENT_FUNDAMENTALS.md](AGENT_FUNDAMENTALS.md).

---

## Contents

1. [The 30-second pitch](#1-the-30-second-pitch)
2. ["Everyone builds this"](#2-everyone-builds-this--how-to-answer)
3. [The problem](#3-the-problem)
4. [Real project or portfolio toy?](#4-real-project-or-portfolio-toy)
5. [What the system does](#5-what-the-system-does)
6. [Architecture](#6-architecture)
7. [Core USPs](#7-core-usps)
8. [Design trade-offs](#8-design-trade-offs)
9. [Limitations](#9-limitations)
10. [How to present it](#10-how-to-present-it)
11. [Anticipated questions](#11-anticipated-questions)
12. [Positioning alongside the other projects](#12-positioning-alongside-the-other-projects)
13. [Demo script](#13-demo-script)
14. [Resume line](#14-resume-line)
15. [Honesty checklist](#15-honesty-checklist--what-not-to-claim)
16. [An honest assessment](#16-an-honest-assessment)

---

## 1. The 30-second pitch

> Code Guardian is a multi-agent code reviewer. An LLM supervisor decides which
> specialist auditors a given diff actually needs — security, performance, both,
> or neither. Bandit runs inside the security auditor, so every finding carries
> whether the LLM found it, the scanner found it, or both did independently.
> Findings become a risk score, a patch and a regression test. And if an audit
> fails, the system **never** says "no issues found" — it marks the whole review
> incomplete.
>
> The routing is measured, on a **held-out** set: as-shipped security recall
> 100%, zero false negatives, on data that was never tuned against.

Three things are deliberate here: **the model decides control flow**, **a
deterministic scanner is fused with the LLM**, and **failure is distinct from
silence**.

---

## 2. "Everyone builds this" — how to answer

**This question will come, and it is not wrong.** AI code review is crowded —
CodeRabbit, Greptile, Qodo, Sourcery, GitHub's own review. And "LangGraph
multi-agent project" is currently the most common portfolio project in agentic AI.

So **do not sell the product.** If you do, the honest response is "everyone builds
this", and they would be right.

### The answer

> "This was not built as a product. I chose the domain because its ground truth is
> measurable — I can tell you whether my agent routed correctly. What I set out to
> show is orchestration and failure handling, not code review."

That is attack-proof, because you are not making the claim they can break.

### Three things other candidates will not have

The idea is common; these three almost never appear in portfolio projects:

1. **The silent-pass bug story.** The system once reported "0 findings" on code
   with a Critical SQL injection, because `ToolNode` turns an exception into a
   plain text message. Caught it, fixed it at schema level, pinned it with tests.
   And it **showed up again in production** — a Groq rate limit hit, and the
   system said `unknown — incomplete` rather than `0/100 clean`. You can demo it
   live.
2. **The agent is measured, on a held-out set.** Most people never measure their
   agent. Those who do rarely hold a set back.
3. **A deterministic scanner fused with the LLM**, with provenance tagging. Most
   portfolio projects are pure-LLM and have no structural answer to "what if it
   hallucinates?".

### What not to lead with

LangGraph, StateGraph, multi-agent, FastAPI, Docker — **table stakes**. Start
there and the project reads as average. Keep them in the background.

**Put plainly:** the architecture is not this project's strength — that part is
average. The engineering judgement is, and that part is not. Full assessment in §16.

---

## 3. The problem

Manual review is slow and misses subtle defects — SQL injection, resource leaks,
N+1 queries.

But the real question is: **why is "just prompt an LLM to review it" not enough?**

| Problem | Naive prompt | Here |
|---|---|---|
| One generalist prompt cannot deeply audit security *and* performance | shallow on both | separate personas, focused criteria |
| Full cost on every submission | full security analysis on a CSS file | the router decides — CSS takes ~0.9s |
| The LLM said nothing — did it miss, or never run? | indistinguishable | `failed_audits` is a separate state |
| The LLM can hallucinate | no second opinion | Bandit fused, `confirmed` tag |

---

## 4. Real project or portfolio toy?

Honest answer: **a working system that would need work before production.**

What is real:
- The Docker stack runs; both entry points (UI and webhook) verified live
- 99 unit tests, no API key required
- Routing recall is **measured** on a held-out set, not assumed
- Six bugs came out of real runs (§9 and the walkthrough)

What is not:
- The PR bot has never run against a real repository
- One language of static scanning (Bandit is Python-only)
- No persistence — every review is stateless
- Eval numbers are from `gpt-oss-20b`, not the default 120b

Saying this distinction out loud lands well. Claiming "production-ready" and then
being caught is the worst outcome available.

---

## 5. What the system does

```
code / PR diff
   → high-stakes check (auth/DB/exec keywords?) → forced fan-out
   → otherwise the supervisor LLM routes (bind_tools, temperature 0)
   → ToolNode, parallel execution
        security_audit    = LLM + Bandit, merged, deduped by line
        performance_audit = Big-O, N+1, leaks, unclosed resources
   → collect: unpack ok/error envelope, sort by severity, score risk
   → patch: model rewrites the file, difflib computes the diff
   → tests (only on Critical/High security): one regression test per finding
   → guardrail: 11 secret patterns + tone, redact rather than drop
   → report + patch + tests + risk + full agent log
```

---

## 6. Architecture

| Component | Tech | Role |
|---|---|---|
| Orchestrator | LangGraph `StateGraph` | supervisor loop, conditional edges, reducers |
| Router | `llm.bind_tools()` + `ToolNode` | the model picks auditors at runtime |
| LLM | Groq `openai/gpt-oss-120b` | tool calling required |
| Scanner | Bandit (subprocess) | deterministic rules, fused into the security audit |
| Scoring | `risk.py` | one triage number, corroboration-aware |
| Safety | custom validators (Guardrails AI optional) | secrets + tone on outbound text |
| API | FastAPI | review, review-pr, health, graph, webhook |
| PR bot | PyGithub | HMAC-verified webhook, reviews added lines |
| UI | React + Vite + Tailwind + Monaco | findings, patch, tests, agent log |

---

## 7. Core USPs

### 7.1 Tool-calling supervisor — the differentiating piece

This is the one place in the portfolio where **the model decides control flow**
(the other two projects let LangGraph edges decide).

A new agent is one more `@tool` with a clear docstring; the graph topology does not
change. **The docstring is the routing logic** — demonstrated: rewriting the
performance tool's docstring as explicit criteria moved its recall from 33% to 50%
without touching a single edge.

### 7.2 Measured routing, on a held-out set

Two labelled sets, two modes. This is the strongest number available:

| Set | Mode | Security recall | Performance recall |
|---|---|---|---|
| dev (tuned against) | router-only | 90% | 50% |
| dev (tuned against) | as-shipped | 100% | 67% |
| **held-out (never tuned)** | router-only | **89%** | 43% |
| **held-out (never tuned)** | as-shipped | **100%** | 57% |

*Measured on `openai/gpt-oss-20b`, 20 cases per set.*

Two things matter here:

- **As-shipped security recall is 100% on data never tuned against.** The backstop
  generalises.
- **The dev/held-out gap is one point** (90 → 89), so the docstring tuning did not
  overfit. Checking that is the part people skip.

The exit code fails below the threshold, and when the held-out set was run the gate
reads *its* number — the only one that is not contaminated.

### 7.3 LLM + deterministic scanner fusion

The scanner cannot miss a pattern it has a rule for and cannot hallucinate one it
does not; the LLM catches what no rule encodes. An `llm+bandit:B608` tag means both
engines saw the same line independently, and severity escalates.

### 7.4 Failure is never silence

`failed_audits` and `audit_errors` are distinct states. A failed audit produces an
"incomplete review" banner and a risk band of `unknown`, never `0/none`.

### 7.5 A risk score calibrated against a gate

One Critical reaches the *high* band, two reach *critical*, because a single
remotely exploitable vulnerability has to be enough to stop a merge.

### 7.6 Fail-closed webhook

No secret configured → 503. `hmac.compare_digest`. 202 plus background work,
because GitHub abandons a delivery after 10 seconds.

---

## 8. Design trade-offs

| Decision | Given up | Why |
|---|---|---|
| Router, not static fan-out | guaranteed coverage | cost and extensibility; the backstop protects recall |
| `difflib` for the diff, not the LLM | "the AI wrote the diff" | LLM-authored diffs routinely fail to apply |
| Bandit fused, not standalone | simplicity | the reviewer reads one list, not two |
| Tests generated, not executed | a "self-healing" claim | sandboxing is a separate project |
| PyGithub, not an MCP server | the "MCP integration" buzzword | MCP's value is model-driven tool choice; these calls are fixed |
| Custom guardrails, Guardrails AI optional | the library name | the torch dependency takes the container into GB |
| Added lines only on PRs | cross-line vulnerabilities | the author cannot act on untouched code in this PR |

---

## 9. Limitations

### L1 — Router false negatives

The biggest risk. **Mitigations:** temperature 0, criteria-style docstrings, the
`looks_high_stakes` backstop, the `force_full_audit` flag, and a recall eval that
gates. **Measured:** as-shipped security recall 100% on both sets.

### L2 — Performance routing is weak, and worse held-out

50% on the dev set, 43% held-out. Unlike security, nothing backstops it.
**Tolerable** only because the errors are asymmetric — and it is now measured
rather than hidden.

### L3 — Bandit is Python-only

Elsewhere the security audit is the LLM alone. **Mitigation:** the `source` field
makes that visible per finding. Semgrep would be one more `_run_*` function.

### L4 — Generated tests are never executed

Deliberate. The report says "generated, not executed".

### L5 — No memory

Every review is stateless. If a developer rejects a suggestion, nothing remembers.
That is Phase 4, and it needs persistence and embeddings.

### L6 — The PR bot has not run against a real repository

Everything up to the GitHub API call is tested; the PyGithub calls are not.

### L7 — Eval numbers are from 20b

The 120b daily quota was exhausted the day they were measured. Re-running is
outstanding.

---

## 10. How to present it

**Structure (3 minutes):**

1. **Problem** (20s) — why "just prompt an LLM" is not enough (the §3 table)
2. **Architecture** (40s) — supervisor routes, auditors run in parallel, patch and
   tests, guardrail
3. **Live demo** (90s) — §13
4. **The bug story** (30s) — the silent clean pass. Close on this; it is what gets
   remembered.

**What to lead with:** *"let me show you a bug I caught in my own system"* — the
fastest proof of technical depth available.

---

## 11. Anticipated questions

### Technical

**Q. Why multi-agent? Wasn't one prompt enough?**
A generalist prompt cannot deeply audit security and performance at once; separate
personas carry focused criteria. And the separation is what makes routing possible,
which is where the cost saving comes from.

**Q. Have you built ReAct-style tool calling?**
Yes — this is that project. Also say *why only here*: in the SQL agent the control
flow should be deterministic (a DB error decides, not the model); here the model's
judgement *is* the routing signal. **Knowing both patterns and when each applies is
the real answer.**

**Q. Why not `create_react_agent`? It's one line.**
It hides the state transitions. The orchestration is this project's reviewable
artifact — hiding it behind a prebuilt defeats the purpose.

**Q. What if the LLM hallucinates?**
Bandit runs inside `security_audit`. The scanner cannot miss its own rules and
cannot invent one. Every finding carries a `source`; where both engines agree it
becomes `llm+bandit:B608` and the severity escalates.

**Q. How do you know the agent actually ran?**
(The best question in the set.) You don't — unless "did not run" is a distinct
state from "ran and found nothing". And this was a real bug, not a hypothetical.

**Q. Why is the state shaped that way?**
`messages` with a reducer (the supervisor loop needs history), findings in separate
lists (separate consumers), `failed_audits` separate (the silent-pass rule), `risk`
computed once so nothing derives its own.

**Q. How would you scale to a 200-file PR?**
Today there is a 10-file cap, ranked by additions. Next: per-file parallelism under
a concurrency limit, and caching by content hash so an unchanged file is not
re-reviewed.

**Q. What does a review cost?**
It has not been measured, so **I will not quote a number**. Structurally: the router
is a small call, the auditors are large ones, and a CSS file triggers zero auditor
calls. Cost tracking is on the roadmap.

### Product

**Q. How is this better than CodeRabbit or Snyk?**
It is not — it is an honest demonstration of the same architecture. What is worth
showing: routing for cost control, LLM+scanner fusion with provenance, and keeping
failure distinct from silence. Commercial tools are often opaque about all three.

**Q. Why would a team trust it?**
Every finding shows its source; an incomplete review says so itself; and the risk
score is calibrated, so the gate behaves predictably.

---

## 12. Positioning alongside the other projects

Three projects: **Adaptive CRAG**, **Self-Healing SQL Agent**, **Code Guardian**.

### "Aren't these the same project three times?"

No, and the difference is **who decides control flow**:

| Project | Who decides | Why |
|---|---|---|
| Adaptive CRAG | LangGraph edges, on an LLM grader's verdict | grading is judgement; routing is deterministic |
| Self-Healing SQL | the database's error message | the error is a deterministic signal; no model opinion needed |
| **Code Guardian** | **the model, via tool calling** | "which audit is this diff worth" is judgement |

That is what makes the three strong together: **you know when to hand the model
control and when not to.** It is not one pattern repeated three times.

### Which to lead with

- **Agentic / LLM-orchestration role** → Code Guardian (tool calling + eval)
- **RAG role** → Adaptive CRAG
- **Data / backend role** → Self-Healing SQL

---

## 13. Demo script

Three scenarios, in this order, about two minutes total.

### Scenario 1 — Vulnerable Python (the money shot)

Load the sample, hit Review.

Show:
- **Risk 100/100 critical** in the run strip
- **3 findings marked `confirmed`** — both engines, independently
- **2 SQLi sites only Bandit caught**
- Patch tab → side-by-side original vs patched
- **Agent log** → "routing bypassed — high-stakes heuristic"

### Scenario 2 — Plain CSS (the architecture shot)

Same flow, CSS sample. **~0.9s versus ~11.4s**, and the run strip shows both
auditors as *skipped*.

> *"The router decided a CSS file has no security surface. A static fan-out would
> have paid full price here too."*

The contrast lands harder than any explanation.

### Scenario 3 — The failure (if there is time)

Set `GUARDIAN_MODEL` to a nonsense id and re-run.

> *"This is the bug I caught. It used to report '0 findings' on code with a
> Critical SQL injection. Now the whole review is marked incomplete."*

**Before demoing:**
```bash
curl https://api.groq.com/openai/v1/models -H "Authorization: Bearer $GROQ_API_KEY"
```
Groq retires model ids, and the free tier is 200k tokens/day per model. Do not burn
the quota the day before.

---

## 14. Resume line

> **Code Guardian** — Multi-agent code reviewer (LangGraph + Groq) where an LLM
> supervisor selects specialist auditors at runtime via `bind_tools`; Bandit static
> analysis fused with LLM findings under provenance tagging; risk scoring,
> autonomous patch and regression-test generation, and an HMAC-verified GitHub PR
> bot. Routing quality measured on a **held-out** set — 100% security recall.

---

## 15. Honesty checklist — what NOT to claim

| ❌ Don't say | ✅ Say |
|---|---|
| "I used Guardrails AI" | "Custom validators; Guardrails AI is optional, and the report names which engine ran" |
| "It has MCP integration" | "It's PyGithub. The model-driven tool calling is in the supervisor" |
| "It's self-healing" | "Tests are generated, not executed — sandboxing is a separate project" |
| "It runs in production" | "It's a working system; the PR bot has not been verified against a real repo" |
| "The router is 100% accurate" | "As-shipped security recall is 100% on a held-out set of 20; router-only is 89%. Performance routing is 43% — that's the weak spot" |
| "Performance auditing is strong" | "Routing recall 43% held-out — the known weakness" |
| "It cuts cost by X%" | "CSS 0.9s versus 11.4s; per-review cost is not measured" |

**The rule: anything not measured does not become a number.**

---

## 16. An honest assessment

### The strength is not the architecture

Supervisor pattern, LangGraph, tool calling — all documented patterns. No
interviewer is impressed by them.

**The strength is that the system is honest about its own failure modes, and that
honesty is enforced in code:**

- A failed audit *cannot* stay silent — enforced at schema level
- An incomplete review *cannot* look safe — enforced in the risk score
- A finding's source *cannot* be hidden — enforced in the `Finding` schema
- Routing quality *cannot* be merely claimed — the eval gates it, on a held-out set

That is engineering judgement rather than library knowledge, and it is the part
portfolio projects usually lack.

### Weaknesses — know these before you are asked

1. **Performance routing is weak** — 50% dev, 43% held-out, and unbackstopped.
2. **Bandit is Python-only**, so the multi-language claim is thin.
3. **The PR bot is unverified against a real repository.**
4. **No persistence or memory** — every review is stateless.
5. **20 cases per set is small** — the interval around 100% is wide.
6. **Eval numbers are from 20b**, not the default 120b.

For each of these you have either a mitigation or a deliberate-deferral reason.
Where you have neither, concede it — that is the best available answer.
