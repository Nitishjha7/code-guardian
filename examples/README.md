# examples/

Deliberately vulnerable code, kept so the PR bot has something real to review on
a real pull request.

**Nothing here is imported by the application, and nothing here is under test.**
`vulnerable_user_service.py` contains SQL injection, shell injection, an unsafe
`pickle.loads`, an `eval()` on caller input, a hardcoded credential and a leaked
file handle — all on purpose.

Bandit and the security auditor are both expected to light up on this file. That
is the point: the review that this repository's own PR bot posts on it is the
verification that the webhook path works end to end, not just the local API.
