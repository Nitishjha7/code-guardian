"""Output guardrails: nothing leaves this system carrying a secret.

Per docs/TECHNICAL_SPEC.md §2 the guard has two jobs — scan emitted diffs for
credential leaks, and keep the tone of automated PR comments civil.

Implementation note, stated plainly: ``guardrails-ai`` is used when it is
installed, but it is an optional dependency (some of its validators pull a full
torch install, which is a poor trade for a container that otherwise fits in a
few hundred MB). When it is absent this module falls back to a local
pattern-based scanner. The fallback is the one that runs by default, so it is
written to be the real guard rather than a placeholder — and the report says
which engine produced the result, so a reviewer is never misled about it.
"""

from __future__ import annotations

import re
from typing import Any, TypedDict

try:  # pragma: no cover - depends on optional install
    from guardrails import Guard  # type: ignore
    from guardrails.hub import SecretsPresent  # type: ignore

    _GUARDRAILS_AVAILABLE = True
except Exception:  # ImportError, or hub validator not downloaded
    _GUARDRAILS_AVAILABLE = False


class GuardrailReport(TypedDict):
    engine: str
    passed: bool
    secrets_found: list[str]
    tone_flags: list[str]
    redactions: int


# Patterns are ordered most-specific first; each captures the *kind* of secret so
# the report can name it without ever echoing the value back.
_SECRET_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("AWS access key id", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")),
    ("GitHub token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,}\b")),
    ("Groq API key", re.compile(r"\bgsk_[A-Za-z0-9]{20,}\b")),
    ("OpenAI API key", re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b")),
    ("Slack token", re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b")),
    ("Google API key", re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b")),
    ("Stripe key", re.compile(r"\b[rs]k_(?:live|test)_[A-Za-z0-9]{16,}\b")),
    ("JSON Web Token", re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b")),
    ("private key block", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    (
        "database connection string with password",
        re.compile(r"\b\w+://[^\s:/@]+:[^\s:/@]+@[^\s/]+", re.IGNORECASE),
    ),
    (
        "hardcoded credential assignment",
        re.compile(
            r"""(?ix)
            \b(?:password|passwd|pwd|secret|api[_-]?key|apikey|access[_-]?token|
               auth[_-]?token|client[_-]?secret|private[_-]?key)\b
            \s*[:=]\s*
            (['"])(?!\s*$)(?![A-Za-z_][A-Za-z0-9_]*\s*\1)   # skip empty / bare identifiers
            (?P<value>[^'"\n]{6,})\1
            """
        ),
    ),
]

# Placeholders a model is *supposed* to emit when it removes a secret. Flagging
# these would make the guard cry wolf on exactly the output we want.
_PLACEHOLDER = re.compile(
    r"(?i)^(?:x{3,}|\*{3,}|\.{3,}|<[^>]+>|\{\{?[^}]+\}?\}|"
    r"your[_-]?\w+|changeme|placeholder|redacted|dummy|example|"
    r"os\.environ.*|os\.getenv.*|process\.env\..*|env\[.*\])$"
)

_TONE_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("insulting language about the author", re.compile(r"(?i)\b(stupid|idiot|moron|dumb|garbage|trash|awful|pathetic|incompetent|lazy)\b")),
    ("profanity", re.compile(r"(?i)\b(damn|crap|wtf|shit|fuck\w*)\b")),
    ("personal attack", re.compile(r"(?i)\byou (?:clearly |obviously )?(?:don'?t|do not|can'?t|cannot) (?:know|understand|code|program)\b")),
]


def _scan_secrets(text: str) -> list[tuple[str, str]]:
    """Return ``(kind, matched_text)`` pairs for every secret-looking match."""
    hits: list[tuple[str, str]] = []
    for kind, pattern in _SECRET_PATTERNS:
        for match in pattern.finditer(text or ""):
            value = match.groupdict().get("value") or match.group(0)
            if _PLACEHOLDER.match(value.strip()):
                continue
            hits.append((kind, value))
    return hits


def _redact(text: str, hits: list[tuple[str, str]]) -> tuple[str, int]:
    redacted, count = text, 0
    for _, value in hits:
        if value and value in redacted:
            redacted = redacted.replace(value, "[REDACTED-BY-GUARDRAIL]")
            count += 1
    return redacted, count


def _scan_tone(text: str) -> list[str]:
    return [label for label, pattern in _TONE_PATTERNS if pattern.search(text or "")]


def _guardrails_ai_secret_scan(text: str) -> list[str] | None:
    """Try guardrails-ai. Returns kinds found, or None if it is unusable."""
    if not _GUARDRAILS_AVAILABLE:
        return None
    try:  # pragma: no cover - depends on optional install
        guard = Guard().use(SecretsPresent, on_fail="noop")
        outcome = guard.validate(text)
        if getattr(outcome, "validation_passed", True):
            return []
        return ["secret detected by guardrails-ai SecretsPresent"]
    except Exception:
        return None


def validate_output(*parts: str) -> tuple[list[str], GuardrailReport]:
    """Validate every outbound text fragment.

    Returns the sanitized fragments in the order given, plus a report. Secrets
    are redacted rather than dropped so the reviewer still sees the shape of the
    patch; tone problems are reported but not rewritten, because silently
    editing an agent's words would hide a prompt regression.
    """
    sanitized: list[str] = []
    all_kinds: list[str] = []
    tone_flags: list[str] = []
    redactions = 0

    for part in parts:
        text = part or ""
        hits = _scan_secrets(text)
        cleaned, n = _redact(text, hits)
        redactions += n
        all_kinds.extend(kind for kind, _ in hits)
        tone_flags.extend(_scan_tone(text))
        sanitized.append(cleaned)

    engine = "local-pattern-scanner"
    external = _guardrails_ai_secret_scan("\n".join(parts))
    if external is not None:
        engine = "guardrails-ai + local-pattern-scanner"
        all_kinds.extend(external)

    report: GuardrailReport = {
        "engine": engine,
        "passed": not all_kinds and not tone_flags,
        "secrets_found": sorted(set(all_kinds)),
        "tone_flags": sorted(set(tone_flags)),
        "redactions": redactions,
    }
    return sanitized, report


def describe() -> dict[str, Any]:
    """Introspection for the /api/health endpoint."""
    return {
        "guardrails_ai_installed": _GUARDRAILS_AVAILABLE,
        "secret_patterns": len(_SECRET_PATTERNS),
        "tone_patterns": len(_TONE_PATTERNS),
    }
