# Code Q&A — defending your own code

The code exists and it goes out under your name. An interviewer will not read it;
they will ask *why that line is written that way*. The questions here are the ones
that will come, because they are the code's **decisions**, not its lines.

**How to use this:** read the question, answer it **without looking**. Wherever you
stall is your weak point — and where the interviewer will push. Do not memorise the
answers; every one of them contains a *why*, and the why is the part that survives a
follow-up.

Each section names the file. **Open the code before reading the answer.**

---

## 1. `supervisor.py` — the tool-calling router

[backend/app/agents/supervisor.py](../backend/app/agents/supervisor.py)

### Q1. Why not just run both agents every time? That's simpler.

A static fan-out pays full price on every submission. A pure CSS diff has no
security surface; a config file has no algorithmic complexity. And on large diffs
the specialist prompts are the dominant cost in the system.

Measured: **CSS ~0.9s** (no auditor ran) versus **vulnerable Python ~11.4s**. A
fan-out makes both cost the same.

The second reason matters more: adding an agent is one more `@tool`. The graph
topology stays constant. With a fan-out, every new agent means rewiring edges.

### Q2. Why do the tools take no arguments? Pass the code in.

[supervisor.py:41](../backend/app/agents/supervisor.py#L41)

Then the model would have to **write the entire diff back out** inside its own tool
call. Those input tokens get charged twice, and a large diff risks being truncated —
which means the auditor silently gets half the code.

The code arrives through a `ContextVar`. **Not a module-level dict**: the API serves
concurrent requests, and a global would let two simultaneous reviews audit each
other's code. A ContextVar is copied into each run's own context.

### Q3. What if the router decides wrong? That's your biggest risk.

Yes — and volunteering this is what shows maturity.

**A false negative (skipping the security audit on code that had a vulnerability) is
far worse than wasted tokens.** The errors are not symmetric. Three mitigations:

1. `temperature=0` plus docstrings written as criteria
2. a `force_full_audit` flag and the `looks_high_stakes()` static backstop
3. a labelled eval set that measures **recall** and gates on it

And there is a number: **as-shipped security recall 100%, zero false negatives, on a
held-out set**. Saying "we measure it" is not enough; the number is what makes the
answer land.

### Q4. `looks_high_stakes` is just a regex. Where is the AI in that?

There is none, and there should not be. It is a **backstop** — insurance against the
router's recall risk. Deliberately over-inclusive: a false positive costs one extra
audit, a false negative costs a vulnerability.

If it were an ML model it would have its own false-negative rate, which defeats the
point of a backstop.

### Q5. Wasn't `\b(password)\b` enough? Why the lookarounds?

[supervisor.py:134](../backend/app/agents/supervisor.py#L134)

No — and this was a **real bug**. `\b` does not fire between an underscore and a
letter, because `_` is a word character. So `\bpassword\b` misses:

- `DB_PASSWORD`
- `check_password`

Exactly the names real code uses. A test caught it. The boundaries are now
`(?<![A-Za-z0-9])` / `(?![A-Za-z0-9])`, which treat an underscore as a boundary.

The same bug was sitting in the secrets guard.

### Q6. Why is `route_with_llm` a separate function? It's all in `supervisor_node`.

[supervisor.py:172](../backend/app/agents/supervisor.py#L172)

So the eval can measure **the router alone**. In `supervisor_node` the backstop runs
first — measuring through that would credit the model for cases the backstop caught,
and the recall number would be falsely good.

That is why the eval reports two modes. Reporting only as-shipped is flattering the
model.

---

## 2. `graph.py` — orchestration and the silent pass

[backend/app/graph.py](../backend/app/graph.py)

### Q7. (The most important question) How do you know your agent actually ran?

If this comes up, lead with it — it was a real bug.

Groq retired `llama-3.3-70b-versatile`. Every audit started returning 404.
LangGraph's `ToolNode` turns an uncaught exception into a **plain-text
ToolMessage**; the collector JSON-parsed it, got `[]`, and the system reported
**"0 findings"** on code containing a Critical SQL injection.

For an auditing tool that is the worst possible failure: **silence became
indistinguishable from a pass.**

The fix has three parts:
1. every tool returns a `{"ok": bool, ...}` envelope
2. anything unparseable counts as an **error**, not an empty result
3. the report never prints "No issues found" for an audit that did not run — it
   leads with an "incomplete review" banner

The real answer: *you don't know, unless you make "did not run" a distinct state
from "ran and found nothing".*

### Q8. `_unpack_audit` still accepts a bare array. Isn't that dead code?

[graph.py:43-68](../backend/app/graph.py#L43-L68)

It is forward/backward compatibility, so a tool returning the old shape still
parses. But **anything that fails to parse counts as an error**, and that is the
rule that matters.

### Q9. Why compute the risk score in `collect_node` rather than in the report?

[graph.py:108](../backend/app/graph.py#L108)

It is computed once into state, and the report, API, UI and PR comment all read
*that*. Deriving it separately would give three implementations that drift, and the
number in the UI would stop matching the number in the PR comment.

### Q10. `_route_after_patch` is just an `if`. Why not make that a tool too, for consistency?

[graph.py:162](../backend/app/graph.py#L162)

Consistency is the wrong goal here. §3a's own argument is that the model should own
control flow only where the decision needs **judgement**:

- "Which audit is this diff worth paying for?" — judgement. The model is better.
- "Are there findings worth writing tests for?" — a boolean over state. An `if` is
  **more correct**, and free.

Making it a router tool would also pollute the routing eval — a third tool would
enter the recall numbers.

### Q11. Why does the guardrail run after the report is rendered, not on the findings?

[graph.py:319](../backend/app/graph.py#L319)

Because the model can copy a secret into **prose** — an explanation, a
recommendation. Scanning only the code block would miss it. The report is rendered
first, then the whole text passes through the guard.

---

## 3. `static_analysis.py` — LLM + Bandit fusion

[backend/app/agents/static_analysis.py](../backend/app/agents/static_analysis.py)

### Q12. (Most likely question) If you have Bandit, why the LLM? If you have the LLM, why Bandit?

Neither replaces the other:

- **Bandit** cannot miss a pattern it has a rule for, and **cannot hallucinate** one
  it does not. Its false-positive rate is a known, fixed property of those rules.
- **The LLM** catches what no rule encodes — a missing authorization check, a
  business-logic flaw, an insecure design — and explains it in context.

Measured on the vulnerable-Python sample: **8 raw findings → 5 after dedup**, **3
confirmed by both engines independently**, and **Bandit found 2 SQLi sites the LLM
missed**. Where they agree, severity escalates — the MD5 finding the LLM rated
*High* became *Critical* once Bandit flagged it HIGH/HIGH.

### Q13. Isn't the first line of Bandit's `code` field the offending line?

[static_analysis.py:93](../backend/app/agents/static_analysis.py#L93)

No — and that was my mistake. Bandit returns **numbered context lines**:

```
"2 \n3 DB_PASSWORD = \"hunter2\"\n4 \n"
```

The first is often a neighbouring blank line. Two problems: the reader saw the wrong
line, **and dedup silently broke**, because the hint no longer matched the LLM's
quote of the real line. The line is now selected by `line_number`.

This came out of running it end to end, not from reading the schema.

### Q14. Why containment for dedup instead of exact match? Containment is loose.

[static_analysis.py:212](../backend/app/agents/static_analysis.py#L212)

Because the two engines quote at **different granularity**:

- LLM: `hashlib.md5(raw.encode()).hexdigest() == stored`
- Bandit: `return hashlib.md5(raw.encode()).hexdigest() == stored`

Requiring equality would report every such pair **twice**, and the `confirmed` badge
would never appear — losing the most useful signal the fusion produces.

The guard against looseness is a 12-character floor; below that an exact match is
required, or `x = 1` would swallow everything.

### Q15. On a merge, why keep the LLM's wording rather than Bandit's?

The LLM **explains the issue in context**; Bandit's text is rule-shaped. But the
higher of the two severities wins, and the tag becomes `llm+bandit:B608` so the
corroboration is visible.

A finding two independent engines agree on is the one to read first. Hiding that
would throw away the fusion's biggest benefit.

---

## 4. `risk.py` — scoring

[backend/app/risk.py](../backend/app/risk.py)

### Q16. Where do the weights come from? 50, 25, 8, 3 look arbitrary.

[risk.py:37](../backend/app/risk.py#L37)

They are **calibrated against the bands**, not chosen for roundness:

- one Critical (50) → *high* band
- two Criticals (100) → *critical*
- one High (25) → *medium*; two Highs (50) → *high*

The requirement was: **one remotely exploitable vulnerability must be enough to stop
a merge** once the Check Run gate reads this number.

The first version used `Critical = 40`, which scored a lone Critical as *medium*.
The test written for that property caught it before it shipped.

### Q17. On a failed audit the score is 0 anyway. Why flag it separately?

Because `0/100 none` means *"we looked and found nothing"* — when what actually
happened is that **nothing looked**. That is the silent-pass bug wearing a number.

So it reports `complete: false`, band `unknown`, and names which audit did not run.

### Q18. Why does diff size carry so little weight? Big diffs are riskier.

Review quality does fall with diff size — true. But **a 2000-line clean diff is not
more dangerous than a 5-line SQL injection.**

So size is a multiplier capped at +25%, and when the base is 0 the score stays 0.
Size cannot manufacture risk on its own.

### Q19. Why are performance findings discounted to 0.4×? They're real problems too.

They are, but of a different kind. **A slow query is a cost; a SQL injection is a
breach.**

If three Medium performance notes could outscore one Critical vulnerability, anyone
triaging on this number would be actively misled.

### Q20. Why the worst file on a PR instead of an average? The worst could be an outlier.

The outlier is the point. **A PR is exactly as risky as its most dangerous change.**
An average lets a clean file dilute another file's Critical finding — opening the
gate in precisely the case where it should close.

---

## 5. `validators.py` — guardrails

[backend/app/guardrails_config/validators.py](../backend/app/guardrails_config/validators.py)

### Q21. The README mentions Guardrails AI. Is it actually used?

**Not by default** — and volunteer this, or an accurate question will catch you out.

`guardrails-ai` is used if installed, but it is optional: some of its hub validators
pull a full torch install, a bad trade for a container that otherwise fits in a few
hundred MB.

The default is a local pattern scanner, and not as a placeholder — 11 secret
patterns, placeholder-aware. `guardrail_report.engine` **always** names which engine
ran.

### Q22. Why redact the secret instead of dropping the whole line?

The reviewer needs to see the **shape** of the patch. Removing the line makes the
diff harder to read and hides that anything was there.

The value becomes `[REDACTED-BY-GUARDRAIL]` — the secret does not leave, the context
survives.

### Q23. You report tone problems but don't rewrite them. Isn't that half a job?

No — silently editing the agent's words would **hide a prompt regression**. If an
auditor is writing insulting language, that is a prompt problem and it should be
visible. The guard reports it rather than papering over it.

Secrets are the opposite case: the damage is irreversible once leaked, so there the
guard redacts.

### Q24. Why exclude "garbage" from the tone guard? That is an insult.

In one real run a finding read *"The connection and cursor are created but never
explicitly closed, relying on **garbage collection**."* — correct technical writing.
The guard flagged it as "insulting language about the author".

**A guard that cries wolf on correct technical writing is one people learn to
ignore — and then it protects nothing.** `garbage collection`, `lazy
loading/evaluation`, `dumb terminal` and `trash the cache` are now excluded, while
"this code is garbage" still flags.

---

## 6. `pr_bot.py` — the webhook

[backend/app/pr_bot.py](../backend/app/pr_bot.py)

### Q25. Why not allow the webhook without a secret? It would be convenient in development.

[pr_bot.py:34](../backend/app/pr_bot.py#L34)

Because that endpoint **runs LLM calls and writes into repositories**. Unauthenticated,
it is a denial-of-wallet and a spam vector — anyone can spend your money and post
comments under your name.

"I forgot to set the secret" must never become "anyone can drive this bot". So it
**fails closed**: 503, nothing processed.

### Q26. Why `hmac.compare_digest` rather than `==`?

`==` returns on the first mismatch, which leaks through **timing** how many
characters were correct — an attacker can recover the secret byte by byte.
`compare_digest` compares in constant time.

### Q27. You return 202 and work in the background. What if that work fails?

GitHub **abandons a delivery after 10 seconds**, and a real review takes longer.
Working inline would make every non-trivial PR show as a failed delivery — and
GitHub disables webhooks after repeated failures.

Failures are not hidden: a file whose review crashes appears in the comment as a
**failed audit** rather than being omitted.

### Q28. Why only the added lines? More context should be better.

[github_client.py:144](../backend/app/mcp_clients/github_client.py#L144)

A PR reviewer's job is the **new code**. Flagging a pre-existing issue on an
untouched context line is noise the author **cannot act on in this PR** — and that
is exactly what trains people to ignore bots.

The trade-off, stated honestly: a vulnerability created by the *interaction* between
an added line and an existing one can be missed. That is a current limitation.

### Q29. Isn't the 10-file cap arbitrary?

The number is; having a cap is not. A 200-file PR would fire 400 LLM calls.

What is **not** arbitrary: files are ranked by **additions**, so when the cap bites
it drops trivia rather than substance. Without ranking you would review whichever
files GitHub happened to list first — effectively at random.

### Q30. This is the "MCP client". Did you use an MCP server?

**No.** The folder is called `mcp_clients/` because the spec said so, but the
implementation is PyGithub — and saying so yourself is essential.

Running the MCP server would mean a second (Node) container wrapping REST calls this
backend already makes. **MCP's real value — a model discovering and calling tools at
runtime — does not apply here**, because the PR bot's GitHub calls are fixed and
webhook-driven, not model-chosen.

The model-driven tool calling in this project is in `supervisor.py`. **If you say
"MCP", say it about that.**

---

## 7. The eval — expect the most follow-ups here

[backend/evals/](../backend/evals/)

### Q31. Security recall is 100%. Does that mean the router is perfect?

No, and say so yourself.

Context first: **there are two sets.** `routing_cases.py` is the one the docstrings
were tuned against (performance recall 33% → 50% from its feedback), so its numbers
are optimistic. That is why `routing_cases_holdout.py` exists — 20 cases **never
tuned against**, and deliberately harder: different languages (Go, Java, SQL,
shell), and no-audit cases carrying *token* / *auth* / *query* in harmless positions,
because the backstop keys off exactly those words.

Same model (`gpt-oss-20b`):

| Set | router-only | as-shipped |
|---|---|---|
| dev (tuned) | 90% | 100% |
| held-out | **89%** | **100%** |

A one-point gap means the tuning did not overfit. **Checking that is the part people
skip**, and its presence is what makes the answer strong.

Remaining limitations, volunteered:

1. **20 cases is a small set** — the interval around 100% is wide.
2. **I wrote and labelled the cases myself** — bias is possible.
3. **These numbers are from 20b**, not the default 120b (its daily quota was
   exhausted that day). Re-running on 120b is outstanding.

### Q31b. What is the rule for the held-out set?

Written in `routing_cases_holdout.py`'s own docstring: **if a case fails, neither
the case nor the prompt it failed on may change.**

A held-out set you edit after seeing the score is just a slower dev set. Fixing a
genuine mislabel is the only permitted edit, and it should be obvious enough that
you would have made it before running anything.

### Q32. Performance recall is only 50%. That's bad.

Yes, and it is the honest weak spot. On several snippets the model called the
*security* auditor on performance-only code. On the held-out set it is worse — 43%.

It is tolerable only because **the errors are asymmetric**: a missed performance
audit costs an optimization suggestion; a missed security audit costs a
vulnerability.

And it is now **measured rather than hidden**, which is better than the number
suggests — you cannot improve what you have not baselined.

### Q33. Why two modes? Just give me one number.

Because they answer different questions:

- `router-only` — are the tool docstrings doing their job?
- `as-shipped` — what is the actual risk?

Reporting only as-shipped **flatters the model** (the backstop covers its mistakes).
Reporting only router-only **overstates** the real risk.

### Q34. Why gate on recall and not precision?

Because the errors are not symmetric. Recall drops → a vulnerability is missed.
Precision drops → a little money is wasted.

If only one can fail the build, it is recall. Precision is reported so the cost stays
visible — and it is visible: the backstop takes held-out performance precision down
to 36% with 7 false positives. That is the intended trade, now quantified.

### Q35. Your eval once printed "recall 11%". What happened?

A rate limit — 19 of 20 cases never reached the model, and the runner scored them as
**false negatives**. An infrastructure failure was reported as a model failure.

That is the same class of bug as the silent pass, in the eval itself. Errored cases
are now **excluded** from scoring, and below 80% coverage the runner prints **no
score at all** and exits non-zero.

---

## 8. One thing deliberately not done

### Q36. You generate tests but never run them. Isn't that half the job?

[test_generator.py](../backend/app/agents/test_generator.py)

Safely executing LLM-authored code needs **no network, an escape-proof filesystem, a
hard timeout and resource limits**. That is a separate infrastructure project, not a
review-agent feature.

Writing a test a human reads and runs is the honest **80%**. Claiming "I verified it"
is the dangerous **20%**.

The report says so literally: *"generated, not executed — read them before you trust
them."* If I executed them and the sandbox were imperfect, this tool would itself
become a remote code execution — in a **security** tool.

---

## If nothing else comes to mind

Three principles; everything else derives from them.

1. **"Did not run" and "found nothing" are different states.** From this follow the
   `ok/error` envelope, `failed_audits`, and the risk score's `unknown` band.
2. **The errors are not symmetric.** From this follow the backstop, the recall gate,
   the 0.4× performance discount, and the default-to-security bias.
3. **Anything not measured is not displayed.** From this follow the eval's
   existence, the absence of a cost dashboard, and the eval's own caveats.
