"""Guardrail tests.

These are the parts of the system worth testing without an LLM: the guard is
the last thing between an agent's output and a public PR comment, and its
failure modes are deterministic.
"""

from app.guardrails_config import validate_output


def test_redacts_hardcoded_password_assignment():
    code = 'DB_PASSWORD = "sup3rs3cret-prod-pw"'
    (clean,), report = validate_output(code)

    assert "sup3rs3cret-prod-pw" not in clean
    assert "[REDACTED-BY-GUARDRAIL]" in clean
    assert report["passed"] is False
    assert report["redactions"] == 1


def test_detects_common_token_formats():
    samples = [
        "AKIAIOSFODNN7EXAMPLE",
        "ghp_" + "a" * 36,
        "gsk_" + "b" * 32,
        "postgres://admin:hunter2@db.internal:5432/shop",
    ]
    for sample in samples:
        _, report = validate_output(sample)
        assert report["passed"] is False, f"missed: {sample}"


def test_placeholders_do_not_trip_the_guard():
    """The whole point of the patch agent is to replace secrets with these."""
    code = "\n".join(
        [
            'DB_PASSWORD = os.environ["DB_PASSWORD"]',
            'API_KEY = "<your-api-key>"',
            'TOKEN = "changeme"',
            'SECRET = "xxxxxxxx"',
        ]
    )
    _, report = validate_output(code)
    assert report["secrets_found"] == []
    assert report["passed"] is True


def test_clean_output_passes():
    _, report = validate_output("def add(a, b):\n    return a + b\n")
    assert report["passed"] is True
    assert report["redactions"] == 0


def test_tone_flags_are_reported_but_text_is_not_rewritten():
    comment = "This is stupid code written by someone lazy."
    (clean,), report = validate_output(comment)

    assert clean == comment, "tone problems are reported, not silently edited"
    assert report["tone_flags"]
    assert report["passed"] is False


def test_technical_vocabulary_is_not_mistaken_for_an_insult():
    """Found in a real run: a finding explaining that a cursor was "relying on
    garbage collection" tripped the insult pattern. A guard that cries wolf on
    correct technical writing is a guard people learn to ignore."""
    benign = [
        "The cursor is never closed, relying on garbage collection.",
        "Use lazy loading here to avoid the upfront cost.",
        "This is a dumb terminal, so escape codes do nothing.",
        "Lazy evaluation would avoid materialising the list.",
    ]
    for text in benign:
        _, report = validate_output(text)
        assert report["tone_flags"] == [], text


def test_actual_insults_are_still_flagged():
    for text in ["This code is garbage.", "Whoever wrote this is lazy.", "Stupid design."]:
        _, report = validate_output(text)
        assert report["tone_flags"], text


def test_report_names_the_engine():
    _, report = validate_output("hello")
    assert "local-pattern-scanner" in report["engine"]
