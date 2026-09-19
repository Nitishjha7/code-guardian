"""Cross-review memory: episodic, semantic, long-term.

A single review holds no state — that is the right default. This package is the
exception: three things that should outlive one review, because re-deriving the
same judgement on every PR is worse than remembering it.

The three are scoped differently:

* **episodic** — one row per (code signature, finding, verdict). Global rather
  than per-repo: the same vulnerable shape looks identical in any codebase.
* **semantic** — facts distilled from clusters of episodes that share a verdict,
  e.g. a finding reported four times and never once fixed. Built on episodic.
* **long_term** — explicit per-``repo_id`` preferences, set only by an API call,
  never inferred. ``repo_id`` is the PR bot's ``repo_full_name``, the only
  standing identity here; ad-hoc ``/api/review`` calls have none.

**SQLite, not a vector store.** There is no database in this stack and Groq has
no embeddings API, so a vector store would mean adding both a service and a
provider. The question this needs answered is "has this exact code shape been
seen before", which a normalized text signature answers exactly — approximate
similarity search would be a worse fit at a higher cost.

Fails open: if the file cannot be opened, memory is off and the review runs as
it did before this package existed.
"""
