"""Phase 2 tests: webhook authentication, event filtering, file selection.

All of this is deterministic and network-free, which matters most for the
signature check: it is the only thing standing between a public URL and a bot
that spends money and writes to repositories.
"""

import hashlib
import hmac
import json

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.mcp_clients.github_client import (
    ChangedFile,
    added_lines,
    language_for_path,
    parse_pull_request_event,
    parse_pull_request_url,
)
from app.pr_bot import check_run_verdict, publish_check_run, verify_signature

SECRET = "s3cr3t-webhook-token"


def sign(secret: str, body: bytes) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


# --------------------------------------------------------------------------- #
# Signature verification
# --------------------------------------------------------------------------- #

def test_valid_signature_is_accepted():
    body = b'{"action": "opened"}'
    ok, reason = verify_signature(SECRET, body, sign(SECRET, body))
    assert ok, reason


def test_wrong_secret_is_rejected():
    body = b'{"action": "opened"}'
    ok, _ = verify_signature(SECRET, body, sign("not-the-secret", body))
    assert not ok


def test_tampered_body_is_rejected():
    signature = sign(SECRET, b'{"action": "opened"}')
    ok, _ = verify_signature(SECRET, b'{"action": "closed"}', signature)
    assert not ok


def test_missing_and_malformed_headers_are_rejected():
    body = b"{}"
    assert not verify_signature(SECRET, body, None)[0]
    assert not verify_signature(SECRET, body, "")[0]
    assert not verify_signature(SECRET, body, "deadbeef")[0]
    assert not verify_signature(SECRET, body, "sha1=deadbeef")[0]


def test_unconfigured_secret_fails_closed():
    """An unauthenticated webhook that runs LLM calls is a denial-of-wallet."""
    body = b"{}"
    ok, reason = verify_signature("", body, sign(SECRET, body))
    assert not ok
    assert "not configured" in reason


# --------------------------------------------------------------------------- #
# Event filtering
# --------------------------------------------------------------------------- #

def _event(action="opened", *, draft=False, number=7):
    return {
        "action": action,
        "repository": {"full_name": "acme/widgets"},
        "pull_request": {
            "number": number,
            "draft": draft,
            "title": "Add checkout",
            "head": {"sha": "abc123"},
        },
    }


@pytest.mark.parametrize("action", ["opened", "synchronize", "reopened", "ready_for_review"])
def test_actionable_pull_request_events_are_parsed(action):
    ref = parse_pull_request_event(_event(action))
    assert ref is not None
    assert ref.repo_full_name == "acme/widgets"
    assert ref.number == 7
    assert ref.action == action


@pytest.mark.parametrize("action", ["closed", "labeled", "assigned", "edited", ""])
def test_non_actionable_actions_are_ignored(action):
    assert parse_pull_request_event(_event(action)) is None


def test_draft_pull_requests_are_skipped():
    assert parse_pull_request_event(_event("opened", draft=True)) is None


def test_draft_marked_ready_is_reviewed():
    assert parse_pull_request_event(_event("ready_for_review", draft=True)) is not None


def test_unrelated_payloads_do_not_raise():
    assert parse_pull_request_event({}) is None
    assert parse_pull_request_event({"action": "opened"}) is None
    assert parse_pull_request_event({"action": "opened", "repository": {}}) is None


# --------------------------------------------------------------------------- #
# File selection and diff handling
# --------------------------------------------------------------------------- #

def test_pr_links_are_parsed_in_the_forms_people_actually_paste():
    for text in [
        "https://github.com/acme/widgets/pull/42",
        "http://www.github.com/acme/widgets/pull/42",
        "github.com/acme/widgets/pull/42",
        "  https://github.com/acme/widgets/pull/42/files  ",
        "acme/widgets#42",
    ]:
        ref = parse_pull_request_url(text)
        assert ref is not None, text
        assert ref.repo_full_name == "acme/widgets"
        assert ref.number == 42


def test_things_that_are_not_pr_links_are_rejected():
    for text in [
        "",
        "https://github.com/acme/widgets",
        "https://github.com/acme/widgets/issues/42",
        "https://gitlab.com/acme/widgets/pull/42",
        "just some words",
    ]:
        assert parse_pull_request_url(text) is None, text


# --------------------------------------------------------------------------- #
# Check Run verdict (roadmap 2e)
# --------------------------------------------------------------------------- #

def _file(score, band, complete=True, security=0):
    changed = ChangedFile(filename="a.py", language="python", patch="")
    state = {
        "risk": {"score": score, "band": band, "complete": complete},
        "security_issues": [{"title": "x"}] * security,
        "performance_issues": [],
    }
    return (changed, state)


def test_a_critical_risk_blocks_the_merge():
    conclusion, title, _ = check_run_verdict([_file(100, "critical", security=2)])
    assert conclusion == "failure"
    assert "100/100" in title


def test_one_critical_finding_is_enough_to_block():
    """risk.py is calibrated so a lone Critical reaches the high band."""
    assert check_run_verdict([_file(50, "high", security=1)])[0] == "failure"


def test_a_clean_pr_passes():
    assert check_run_verdict([_file(0, "none")])[0] == "success"


def test_a_low_risk_pr_passes():
    assert check_run_verdict([_file(10, "low", security=1)])[0] == "success"


def test_an_incomplete_review_asks_for_a_human_rather_than_passing():
    """Neither success nor failure is honest when nothing actually looked."""
    conclusion, title, summary = check_run_verdict(
        [_file(0, "unknown", complete=False)]
    )
    assert conclusion == "action_required"
    assert "incomplete" in title.lower()
    assert "not fully checked" in summary


def test_one_incomplete_file_makes_the_whole_verdict_incomplete():
    verdict = check_run_verdict(
        [_file(0, "none"), _file(0, "unknown", complete=False)]
    )
    assert verdict[0] == "action_required"


def test_the_verdict_follows_the_worst_file_not_the_average():
    conclusion, title, _ = check_run_verdict(
        [_file(0, "none"), _file(0, "none"), _file(100, "critical", security=1)]
    )
    assert conclusion == "failure"
    assert "100/100" in title


def test_a_manual_run_publishes_no_check(monkeypatch):
    """Only the webhook carries a head SHA; a pasted link has nothing to attach to."""
    ref = parse_pull_request_url("acme/widgets#7")
    assert publish_check_run(ref, object(), [_file(100, "critical")]) == ""


def test_known_source_extensions_map_to_a_language():
    assert language_for_path("src/app.py") == "python"
    assert language_for_path("web/Button.tsx") == "typescript"
    assert language_for_path("db/schema.sql") == "sql"


def test_non_source_and_generated_files_are_skipped():
    for path in [
        "README.md",
        "logo.png",
        "package-lock.json",
        "poetry.lock",
        "node_modules/left-pad/index.js",
        "static/js/bundle.min.js",
        "app/migrations/0001_initial.py",
    ]:
        assert language_for_path(path) is None, path


def test_added_lines_keeps_only_new_code():
    patch = "\n".join(
        [
            "@@ -1,4 +1,5 @@",
            " def handler(request):",
            "-    return run(request)",
            "+    query = \"SELECT * FROM t WHERE id = \" + request.args['id']",
            "+    return run(query)",
            "+++ b/app.py",
        ]
    )
    result = added_lines(patch)

    assert "SELECT * FROM t" in result
    assert "return run(query)" in result
    # Context and removed lines are not this PR's responsibility.
    assert "return run(request)" not in result
    # The +++ file header is not code.
    assert "b/app.py" not in result


def test_added_lines_on_an_empty_patch_is_empty():
    assert added_lines("") == ""
    assert added_lines(None) == ""


# --------------------------------------------------------------------------- #
# Endpoint behaviour
# --------------------------------------------------------------------------- #

@pytest.fixture()
def client(monkeypatch):
    from app import config

    config.get_settings.cache_clear()
    monkeypatch.setenv("GITHUB_WEBHOOK_SECRET", SECRET)
    monkeypatch.setenv("GROQ_API_KEY", "gsk_test")
    yield TestClient(app)
    config.get_settings.cache_clear()


def _post(client, payload, event="pull_request", secret=SECRET):
    body = json.dumps(payload).encode()
    return client.post(
        "/webhook/github",
        content=body,
        headers={
            "X-Hub-Signature-256": sign(secret, body),
            "X-GitHub-Event": event,
            "Content-Type": "application/json",
        },
    )


def test_webhook_rejects_a_bad_signature(client):
    response = _post(client, _event(), secret="wrong-secret")
    assert response.status_code == 401


def test_webhook_answers_ping(client):
    response = _post(client, {"zen": "Design for failure."}, event="ping")
    assert response.status_code == 202
    assert response.json()["status"] == "pong"


def test_webhook_ignores_unhandled_events(client):
    response = _post(client, {"ref": "refs/heads/main"}, event="push")
    assert response.json()["status"] == "ignored"


def test_webhook_queues_a_review_for_an_opened_pr(client, monkeypatch):
    queued = []
    monkeypatch.setattr(
        "app.pr_bot.review_pull_request", lambda ref: queued.append(ref)
    )

    response = _post(client, _event("opened"))

    assert response.status_code == 202
    assert response.json()["status"] == "queued"
    assert response.json()["pull_request"] == 7
    assert len(queued) == 1
    assert queued[0].repo_full_name == "acme/widgets"


def test_webhook_does_not_queue_a_closed_pr(client, monkeypatch):
    queued = []
    monkeypatch.setattr(
        "app.pr_bot.review_pull_request", lambda ref: queued.append(ref)
    )

    response = _post(client, _event("closed"))

    assert response.json()["status"] == "ignored"
    assert queued == []
