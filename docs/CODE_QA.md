# Code Q&A — apne hi code ko defend karne ke liye

Code ban chuka hai. Wo tere naam se jaayega. Interviewer code padhega nahi — wo
tujhse poochhega *"ye line aise kyun likhi"*. Jo sawaal yahan hain, wahi wahan
aayenge, kyunki ye code ke **faisle** hain — lines nahi.

**Kaise use karna hai:** sawaal padho, jawab **dekhe bina** bolo. Jahan atke, wahi
tera kamzor point — usi pe interviewer bhi atkayega. Jawab yaad mat karo; har jawab
me **kyun** likha hai, wahi samajhna hai. Interviewer follow-up poochhega, aur ratta
wahin toot jaata hai.

Har sawaal ke saath file di hai — jawab padhne se pehle **code kholo**.

---

## 1. `supervisor.py` — tool-calling router

[backend/app/agents/supervisor.py](../backend/app/agents/supervisor.py)

### Q1. Supervisor har baar dono agents kyun nahi chala deta? Simple to wahi hai.

Static fan-out har submission pe poora cost deta hai. Pure CSS diff pe security
surface hai hi nahi; config file me algorithmic complexity nahi hoti. Aur bade diffs
pe specialist prompts hi is system ka sabse bada kharcha hain.

Naapa hua farak: **CSS sample ~0.9s** (koi auditor nahi chala) vs **vulnerable Python
~11.4s**. Fan-out me dono cases barabar mehenge hote.

Doosri wajah zyada important hai: naya agent add karna sirf ek `@tool` likhna hai.
Graph topology same rehti hai. Fan-out me har naye agent pe edges rewire karni padti.

### Q2. Tools zero-argument kyun hain? Code ko parameter bana dete.

[supervisor.py:41](../backend/app/agents/supervisor.py#L41)

Tab model ko poora diff apne tool call me **wapas likhna** padta. Do nuksaan: wo
input tokens **do baar** charge hote, aur bada diff model truncate kar sakta tha —
yaani auditor ko aadha code milta aur wo chup rehta.

Code `ContextVar` se aata hai. **Plain module dict nahi** — API concurrent requests
serve karta hai, aur global dict me do simultaneous reviews ek doosre ka code audit
kar lete. ContextVar har run ke apne context me copy hota hai.

### Q3. Router galat decide kar de to? Ye to tumhara sabse bada risk hai.

Haan, aur ye khud bolna chahiye — yahi maturity dikhata hai.

**False negative (security audit skip ho gaya jabki vulnerability thi) wasted tokens
se kahin bura hai.** Errors symmetric nahi hain. Teen mitigation:

1. `temperature=0` + docstrings *criteria* ki tarah likhi hui
2. `force_full_audit` flag + `looks_high_stakes()` static backstop
3. Labelled eval set jo **recall** naapta hai

Aur number bhi hai: **security recall 100%, 0 false negatives** — dono modes me.
"Hum measure karte hain" bolna kaafi nahi; number bolna is jawab ko strong banata hai.

### Q4. `looks_high_stakes` me regex hi to hai. Ye "AI" kahan hua?

Ye AI hai bhi nahi, aur honi bhi nahi chahiye. Ye ek **backstop** hai — router ke
recall risk ka insurance. Jaan-boojh ke over-inclusive: false positive ek extra audit
ka kharcha hai, false negative ek chhooti hui vulnerability.

Agar ye ML hota to iska apna false-negative rate hota, aur backstop ka matlab hi
khatam ho jaata.

### Q5. `\b(password)\b` kaafi tha na? Lookarounds kyun?

[supervisor.py:134](../backend/app/agents/supervisor.py#L134)

Nahi — aur ye ek **asli bug** tha. `\b` underscore aur letter ke beech fire nahi karta,
kyunki `_` word character hai. Matlab `\bpassword\b`:

- `DB_PASSWORD` — miss
- `check_password` — miss

Yaani wahi naam jo asli code me hote hain. Test ne pakda. Ab `(?<![A-Za-z0-9])` /
`(?![A-Za-z0-9])` hain, jo underscore ko boundary maante hain.

Yahi bug secrets guard me bhi baitha tha.

### Q6. `route_with_llm` alag function kyun hai? `supervisor_node` me hi to sab hai.

[supervisor.py:172](../backend/app/agents/supervisor.py#L172)

Taaki eval **router ko akele** naap sake. `supervisor_node` me backstop pehle chalta
hai — usse naapte to jo cases backstop pakadta hai wo model ke credit me chale jaate,
aur recall jhootha accha dikhta.

Isliye eval do modes report karta hai. Sirf as-shipped dikhana model ko flatter karna
hai.

---

## 2. `graph.py` — orchestration aur silent-pass

[backend/app/graph.py](../backend/app/graph.py)

### Q7. **(Sabse important sawaal)** Tumhe kaise pata ki tumhara agent actually chala?

Ye sawaal aaye to lead isi se karo, kyunki ye ek asli bug tha.

Groq ne `llama-3.3-70b-versatile` retire kar diya. Har audit 404 dene lagi. LangGraph
ka `ToolNode` uncaught exception ko **plain-text ToolMessage** bana deta hai; collector
usko JSON parse karta tha, `[]` milta tha, aur system ne report kiya: **"0 findings"** —
us code pe jisme Critical SQL injection tha.

Ek auditing tool ke liye ye sabse bura failure hai: **silence aur pass me farak hi
khatam ho gaya.**

Fix teen hisson me:
1. Har tool `{"ok": bool, ...}` envelope deta hai
2. Jo parse na ho wo **error** hai, empty result nahi
3. Report failed audit pe kabhi "No issues found" nahi chhapti — "incomplete review"
   banner sabse upar aata hai

Asli jawab: *tumhe pata nahi chalta, jab tak "did not run" ko "ran and found nothing"
se alag state na banao.*

### Q8. `_unpack_audit` me bare array bhi accept karte ho. Dead code nahi hai?

[graph.py:43-68](../backend/app/graph.py#L43-L68)

Forward/backward compatibility ke liye hai — agar koi tool purane format me de, wo
parse ho jaaye. Lekin **jo parse hi na ho wo error count hota hai**, aur wahi asli
rule hai.

### Q9. Risk score `collect_node` me kyun? Report me compute kar lete.

[graph.py:108](../backend/app/graph.py#L108)

Ek jagah compute hoke state me jaata hai, phir report, API, UI aur PR comment sab
**wahi** padhte hain. Alag-alag jagah derive karte to teen implementations divergent
ho jaati aur UI ka number PR comment ke number se match nahi karta.

### Q10. `_route_after_patch` ek `if` hi to hai. Isko bhi tool bana dete, consistent rehta.

[graph.py:162](../backend/app/graph.py#L162)

Consistency galat goal hai yahan. §3a ka apna argument hai: model control flow tabhi
decide kare jab **judgement** chahiye.

- "Kaunsa audit is diff pe worth hai?" — judgement. Model behtar hai.
- "Tests likhne layak findings hain kya?" — boolean over state. Ek `if` **zyada sahi**
  hai, aur free hai.

Aur router tool banate to routing eval ka clean measurement bhi kharab hota — teesra
tool recall numbers me ghus jaata.

### Q11. Guardrail report render karne ke baad kyun chalta hai? Findings pe hi laga dete.

[graph.py:319](../backend/app/graph.py#L319)

Kyunki model secret ko **prose me** copy kar sakta hai — explanation me, recommendation
me. Sirf code block scan karte to wo nikal jaata. Report pehle render hoti hai, phir
poora text guard se guzarta hai.

---

## 3. `static_analysis.py` — LLM + Bandit fusion

[backend/app/agents/static_analysis.py](../backend/app/agents/static_analysis.py)

### Q12. **(Sabse zyada poochha jaane wala)** Bandit hai to LLM kyun? Ya LLM hai to Bandit kyun?

Koi ek doosre ko replace nahi karta:

- **Bandit** apne rule set pe kabhi miss nahi karta, aur jo rule nahi hai wo
  **hallucinate kar hi nahi sakta**. Uska false-positive rate ek known, fixed property
  hai.
- **LLM** wo pakadta hai jo kisi rule me likha nahi — missing authorization check,
  business-logic flaw, insecure design — aur context ke saath samjhata hai.

Naapa hua: vulnerable Python pe **8 raw findings → 5** dedup ke baad, **3 dono engines
ne independently confirm kiye**, aur **Bandit ne 2 SQLi sites pakde jo LLM se chhoot
gaye the**. Agreement pe severity escalate hui — MD5 wala finding LLM ne *High* kaha
tha, Bandit ke HIGH/HIGH confirm karne pe *Critical* ho gaya.

### Q13. Bandit ke `code` field ki pehli line hi to offending line hogi?

[static_analysis.py:93](../backend/app/agents/static_analysis.py#L93)

Nahi — aur maine yahi galti ki thi. Bandit **numbered context lines** deta hai:

```
"2 \n3 DB_PASSWORD = \"hunter2\"\n4 \n"
```

Pehli line aksar padosi blank line hoti hai. Do nuksaan the: reader ko galat line
dikhti thi, **aur dedup chupke se toot gaya tha** kyunki hint LLM ke quote se match hi
nahi karta tha. Ab line `line_number` se select hoti hai.

Ye end-to-end chalane se mila, schema padh ke nahi.

### Q14. Dedup me exact match kyun nahi? Containment to loose hai.

[static_analysis.py:212](../backend/app/agents/static_analysis.py#L212)

Kyunki dono engines **alag granularity** pe quote karte hain:

- LLM: `hashlib.md5(raw.encode()).hexdigest() == stored`
- Bandit: `return hashlib.md5(raw.encode()).hexdigest() == stored`

Equality maangte to har aisa pair **do baar** report hota, aur `confirmed` badge kabhi
lagta hi nahi — yaani fusion ka sabse useful signal gayab.

Loose hone ka bachaav: 12-char length floor. Usse chhoti lines pe exact match chahiye,
warna `x = 1` sab kuch nigal leta.

### Q15. Merge me LLM ki wording kyun rakhi, Bandit ki kyun nahi?

LLM issue ko **context me samjhata** hai; Bandit ka text rule-shaped hota hai. Lekin
severity wahi lete hain jo zyada severe ho, aur tag `llm+bandit:B608` ban jaata hai
taaki corroboration dikhe.

Jispe do independent engines agree karte hain, wahi finding sabse pehle padhni chahiye
— usko chhupana fusion ka sabse bada faayda phenkna hai.

---

## 4. `risk.py` — scoring

[backend/app/risk.py](../backend/app/risk.py)

### Q16. Weights kahan se aaye? 50, 25, 8, 3 — random to nahi?

[risk.py:37](../backend/app/risk.py#L37)

Bands ke **against calibrated** hain, roundness ke liye nahi chune:

- Ek Critical (50) → *high* band
- Do Critical (100) → *critical*
- Ek High (25) → *medium*; do High (50) → *high*

Requirement ye thi: **ek remotely exploitable vulnerability merge rokne ke liye kaafi
honi chahiye**, jab Check Run gate ye number padhega.

Pehla version `Critical = 40` tha — ek akela Critical *medium* dikh raha tha. Property
ke liye likhe test ne ship hone se pehle pakad liya.

### Q17. Failed audit pe score 0 hi to hai. Phir alag flag kyun?

Kyunki `0/100 none` ka matlab hota hai *"dekha, kuch nahi mila"* — jabki hua ye hai ki
**kisi ne dekha hi nahi**. Wo silent-pass bug hi hai, bas ek number ki shakal me.

Isliye `complete: false`, `band: "unknown"`, aur note me likha hota hai kaunsa audit
nahi chala.

### Q18. Diff size ko itna kam weight kyun? Bada diff to zyada risky hota hai.

Review quality diff size ke saath girti hai — ye sach hai. Lekin **2000-line clean
diff ek 5-line SQL injection se zyada khatarnak nahi hai.**

Isliye size ek multiplier hai, +25% pe capped, aur base 0 ho to score 0 hi rehta hai.
Size apne aap risk manufacture nahi kar sakta.

### Q19. Performance findings 0.4× kyun? Wo bhi to asli problem hain.

Hain, lekin alag category ki. **Slow query ek cost hai; SQL injection ek breach hai.**

Agar teen Medium performance notes ek Critical vulnerability se zyada score kar jaate,
to jo banda is number pe triage karta hai wo actively misled hota.

### Q20. PR pe average kyun nahi lete? Worst file to outlier ho sakta hai.

Outlier hi to point hai. **Ek PR utna hi risky hai jitna uska sabse khatarnak change.**
Average lete to ek clean file dusri file ki Critical finding ko dilute kar deti — aur
gate exactly us case me khul jaata jab band hona chahiye tha.

---

## 5. `validators.py` — guardrails

[backend/app/guardrails_config/validators.py](../backend/app/guardrails_config/validators.py)

### Q21. Tumne "Guardrails AI" likha hai README me. Wo actually use ho rahi hai?

**Default me nahi.** Aur ye khud bolna hai, warna ek accurate sawaal pe phas jaoge.

`guardrails-ai` installed ho to use hoti hai, lekin optional dependency hai — uske kuch
hub validators poora torch kheench lete hain, jo ek aise container ke liye bura trade
hai jo warna kuch sau MB ka hai.

Default local pattern scanner hai, aur wo placeholder ke taur pe nahi — 11 secret
patterns, placeholder-aware. `guardrail_report.engine` **hamesha** batata hai kaunsa
engine chala.

### Q22. Secret redact karte ho, poori line drop kyun nahi?

Reviewer ko patch ki **shakal** dikhni chahiye. Line gayab kar dete to diff padhna
mushkil ho jaata aur reviewer ko pata hi nahi chalta ki wahan kya tha.

Value `[REDACTED-BY-GUARDRAIL]` ban jaati hai — secret bahar nahi jaata, context
bacha rehta hai.

### Q23. Tone problems report karte ho par text rewrite nahi karte. Adhoora nahi lagta?

Nahi — agent ke shabd chupke se badalna ek **prompt regression chhupa dena** hai.
Agar auditor insulting language likh raha hai to wo prompt ki problem hai, aur usko
dikhna chahiye. Guard uski report karta hai, maskup nahi.

Secrets alag case hai: wahan nuksaan irreversible hai (leak ho gaya to ho gaya), isliye
wahan redact karte hain.

### Q24. Tone guard me "garbage" exclude kyun kiya? Wo to insult hi hai.

Ek asli run me finding likhi thi: *"The connection and cursor are created but never
explicitly closed, relying on **garbage collection**."* — bilkul sahi technical baat.
Guard ne use "insulting language about the author" flag kar diya.

**Jo guard correct technical writing pe cry-wolf karta hai, log usse ignore karna
seekh jaate hain — aur tab wo kuch bhi protect nahi karta.** Ab `garbage collection`,
`lazy loading/evaluation`, `dumb terminal`, `trash the cache` excluded hain, par
"this code is garbage" ab bhi flag hota hai.

---

## 6. `pr_bot.py` — webhook

[backend/app/pr_bot.py](../backend/app/pr_bot.py)

### Q25. Secret na ho to webhook allow kyun nahi kar dete? Development me convenient hota.

[pr_bot.py:34](../backend/app/pr_bot.py#L34)

Kyunki wo endpoint **LLM calls chalata hai aur repos me likhta hai**. Bina auth ke wo
ek denial-of-wallet aur spam vector hai — koi bhi tumhare paise kharch kara sakta hai
aur tumhare naam se comments post kara sakta hai.

"Secret set karna bhool gaya" kabhi "koi bhi bot chala sakta hai" nahi banna chahiye.
Isliye **fail closed**: 503, kuch process nahi hota.

### Q26. `hmac.compare_digest` kyun, `==` kyun nahi?

`==` pehle mismatch pe return kar deta hai. Wo **timing** se batata hai ki kitne
characters sahi the — attacker ek-ek byte guess karke secret nikal sakta hai.
`compare_digest` constant time me compare karta hai.

### Q27. 202 return karke background me kaam? Agar wo fail ho gaya to?

GitHub ek delivery ko **10 second** baad abandon kar deta hai, aur asli review usse
zyada leta hai. Inline karte to har non-trivial PR webhook log me *failed delivery*
dikhta — aur GitHub repeated failures pe webhook disable kar deta hai.

Failure chhupti nahi: har file jiska review crash hota hai wo **failed audit** ke roop
me comment me aata hai, omit nahi hota.

### Q28. Poori file review kyun nahi karte? Zyada context to behtar hota hai na.

[github_client.py:144](../backend/app/mcp_clients/github_client.py#L144)

PR reviewer ka kaam **naya code** hai. Untouched context line pe pre-existing issue
flag karna wo noise hai jispe author **is PR me kuch kar hi nahi sakta** — aur wahi
cheez bots ko ignore karwati hai.

Trade-off imaandaari se: added lines me wo vulnerability chhoot sakti hai jo added
line + purani line ke **interaction** se banti hai. Wo abhi ki limitation hai.

### Q29. 10 files ka cap arbitrary nahi hai?

Cap ka number arbitrary hai; cap hona nahi. 200-file PR pe 400 LLM calls chalti.

Jo arbitrary **nahi** hai: files **additions ke hisaab se ranked** hain. Cap lage to
trivia kate, substance nahi. Bina ranking ke jo file GitHub pehle list karta wahi
review hoti — yaani random.

### Q30. Ye "MCP client" hai. MCP server use kiya?

**Nahi.** Folder ka naam `mcp_clients/` hai kyunki spec me wo likha tha, par
implementation PyGithub hai — aur ye khud bolna zaroori hai.

MCP server chalane ka matlab hota ek aur (Node) container sirf un REST calls ko wrap
karne ke liye jo backend already karta hai. **MCP ki asli value — model runtime pe
tools discover aur call kare — yahan lagti hi nahi**, kyunki PR bot ki GitHub calls
fixed aur webhook-driven hain, model-chosen nahi.

Is project me model-driven tool calling `supervisor.py` me hai. **"MCP" bolo to uske
baare me bolo.**

---

## 7. Eval — sabse zyada follow-up yahin aayega

[backend/evals/](../backend/evals/)

### Q31. Security recall 100% hai. Matlab router perfect hai?

Nahi, aur ye khud bolna hai. Teen wajah:

1. **20 cases hain.** Ek chhota set hai; 100% ka confidence interval chauda hai.
2. **Maine hi cases likhe aur maine hi label lagaye** — bias possible hai.
3. **Sabse important: maine isi set pe tune kiya.** Performance docstring iske
   feedback se badli (recall 33% → 50%). Yaani set **held-out nahi hai**, numbers
   optimistic hain. Fresh set kam score karega.

Ye README me bhi likha hai. Regression gate banana ho to naye cases likhne padenge
aur unpe tune nahi karna hoga.

### Q32. Performance recall sirf 50% hai. Ye to kharab hai.

Haan, aur yahi is system ka imaandaar weak spot hai. Teen snippets pe model ne
performance-only code pe *security* auditor bula liya.

Tolerable sirf isliye hai ki **errors asymmetric hain**: chhoota performance audit
ek optimization suggestion ka nuksaan hai; chhoota security audit ek vulnerability ka.

Aur ab ye **naapa hua** hai, chhupa hua nahi — jo is number ko pehle se better banata
hai, kyunki improve karne ke liye baseline chahiye.

### Q33. Do modes kyun? Ek number bolo na.

Kyunki dono alag sawaal ka jawab dete hain:

- `router-only` — kya tool docstrings apna kaam kar rahi hain?
- `as-shipped` — asli risk kya hai?

Sirf as-shipped bolna **model ko flatter** karna hai (backstop uski galtiyan pakad
leta hai). Sirf router-only bolna asli risk **overstate** karna hai.

### Q34. Precision gate kyun nahi hai? Sirf recall pe fail hota hai.

Kyunki errors symmetric nahi hain. Recall gire → vulnerability chhooti. Precision gire
→ kuch paise zyada lagte.

Ek hi cheez pe fail karna hai to wo recall hai. Precision report hoti hai taaki cost
dikhe — aur wo dikhti bhi hai: backstop as-shipped performance precision 33% kar deta
hai, 8 false positives ke saath. Wo intended trade hai, ab quantified.

---

## 8. Ek cheez jaan-boojh ke nahi ki

### Q35. Tests generate karte ho par chalate nahi. Aadha kaam nahi hai?

[test_generator.py](../backend/app/agents/test_generator.py)

LLM ke likhe code ko safely chalane ke liye chahiye: **no network, escape-proof
filesystem, hard timeout, resource limits.** Wo ek alag infrastructure project hai,
review agent ka feature nahi.

Test likh ke dena jise insaan padhe aur chalaye — imaandaar **80%**.
"Maine verify kar liya" bolna — khatarnak **20%**.

Report me literally likha hai: *"generated, not executed — read them before you trust
them."* Agar main unhe chalata aur sandbox theek se na hota, to ye tool khud ek
remote code execution ban jaata — ek **security** tool.

---

## Agar kuch na aaye

Teen cheezein yaad rakho, baaki inse derive ho jaayengi:

1. **"Did not run" aur "found nothing" alag states hain.** Isse `ok/error` envelope,
   `failed_audits`, risk ka `unknown` band — sab nikalta hai.
2. **Errors asymmetric hain.** Isse backstop, recall gate, performance ka 0.4×
   discount, aur default-to-security bias — sab nikalta hai.
3. **Jo naapa nahi gaya, wo dikhaya nahi jaata.** Isse eval ka hona, cost dashboard ka
   na hona, aur eval ka caveat — sab nikalta hai.
