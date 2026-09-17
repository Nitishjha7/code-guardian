"""Cross-review memory: episodic, semantic, long-term.

Everything else in this project is stateless by design - one review, one
request, no state carried anywhere (see docs/TECHNICAL_SPEC.md). That is the
right default for a code-review tool with no auth and no notion of "session".
This package is the deliberate exception: three things that *should* survive
past a single review, because a reviewer that re-derives the same judgement
from scratch on every PR is worse than one that remembers what it already
found.

Each of the three is scoped differently, and that difference is the whole
design:

* **episodic** (``episodic.py``) - one row per (file signature, finding).
  Global, not scoped to a repo: a hardcoded-secret pattern looks the same in
  any codebase, so there is no reason to silo it per repo.
* **semantic** (``semantic.py``) - facts distilled from *clusters* of
  episodes that share a repeated verdict, e.g. "this exact snippet shape was
  flagged 4 times and dismissed as a false positive every time." Built from
  episodic, not independent of it - same relationship as
  self-healing-sql-agent's semantic memory to its episodic memory.
* **long_term** (``long_term.py``) - explicit, per-``repo_id`` review
  preferences (severity thresholds to suppress, auditors to skip), set only
  by an explicit call, never inferred from a review's content. ``repo_id`` is
  ``PullRequestRef.repo_full_name`` (``app/mcp_clients/github_client.py``) -
  the only standing identity this project has, since reviews triggered via
  the ad-hoc ``/api/review`` endpoint have no PR and no repo at all.

**Why SQLite and not pgvector, unlike the sibling sql-agent project:** this
project has no database of any kind today (docker-compose.yml has no `db`
service) and only one LLM provider, Groq, which has no embeddings API - so a
genuine vector store is not on the table without adding both a new service
and a new provider key. SQLite is the stdlib, needs no new container, and the
similarity this package actually needs (has this near-identical code shape
been seen before) is answered well enough by comparing a normalized-AST-ish
text signature, not by semantic embedding search. Reaching for pgvector here
would be solving a problem this project does not have at the cost of
infrastructure it does not otherwise need.

Fails open like every other optional feature in this codebase: if the SQLite
file cannot be opened or written, memory is silently off and a review runs
exactly as it did before this package existed.
"""
