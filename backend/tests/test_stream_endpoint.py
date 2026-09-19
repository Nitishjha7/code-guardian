"""The SSE endpoint must actually stream, not buffer.

``run_review_stream`` yielding incrementally (test_graph.py) does not mean the
HTTP layer forwards incrementally. It shipped not doing so: the endpoint awaited
the producer to completion before draining its queue, so every event arrived in
one burst *after* the review had already finished. The payload contract was
correct and only the timing was wrong, which is precisely what the generator
tests could not see.

These tests therefore run a **real uvicorn server** rather than ``TestClient``
or ``httpx.ASGITransport``. Both of those buffer the whole response before
handing back the first line - measured against a deliberately stalled producer,
they report identical timings for the buffered and the streaming implementation,
so a test built on either passes against the bug it is supposed to catch.
"""

from __future__ import annotations

import socket
import threading
import time

import httpx
import pytest
import uvicorn

# How long the fake producer stalls between its first and last event. The
# assertions only need to tell "arrived together" from "arrived apart", so this
# is comfortably above scheduler noise without making the suite slow.
STALL_SECONDS = 2.0


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _blank_state(language: str) -> dict:
    """The minimum ``_review_response`` needs to build a ReviewResponse."""
    return {
        "language": language, "routed_to": [], "failed_audits": [], "audit_errors": [],
        "security_issues": [], "performance_issues": [], "fixed_code": "", "diff": "",
        "summary_report": "", "logs": [], "guardrail_report": {},
    }


@pytest.fixture
def server(monkeypatch):
    """A real uvicorn server on a free port, serving ``app.main.app``.

    Yields a ``run(fake_stream)`` helper that installs a stand-in for
    ``run_review_stream`` (no LLM calls) and returns the timestamped events.
    """
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    import app.main as main_module

    port = _free_port()
    config = uvicorn.Config(main_module.app, host="127.0.0.1", port=port, log_level="error")
    uv = uvicorn.Server(config)
    thread = threading.Thread(target=uv.run, daemon=True)
    thread.start()

    deadline = time.time() + 20
    while not uv.started and time.time() < deadline:
        time.sleep(0.02)
    if not uv.started:
        pytest.fail("uvicorn did not start")

    def run(fake_stream) -> list[tuple[float, str]]:
        monkeypatch.setattr(main_module, "run_review_stream", fake_stream)
        started = time.time()
        events: list[tuple[float, str]] = []
        with httpx.Client(base_url=f"http://127.0.0.1:{port}", timeout=30) as client:
            with client.stream(
                "POST", "/api/review/stream", json={"source_code": "x = 1"}
            ) as response:
                assert response.status_code == 200
                for line in response.iter_lines():
                    if line.startswith("event: "):
                        events.append((time.time() - started, line.removeprefix("event: ")))
        return events

    try:
        yield run
    finally:
        uv.should_exit = True
        thread.join(timeout=10)


def test_events_are_forwarded_as_they_are_produced(server):
    """The regression test for the burst bug.

    The producer stalls mid-run. If the endpoint streams, the first event lands
    before the stall and the last one after it. If it buffers, both arrive
    together once the whole review is over.
    """
    def fake_stream(source_code, language="python", force_full_audit=False, repo_id=""):
        yield "progress", {"node": "supervisor", "label": "routing", "elapsed_ms": 1}
        time.sleep(STALL_SECONDS)
        yield "done", _blank_state(language)

    events = server(fake_stream)
    assert [name for _, name in events] == ["progress", "done"]

    first_at, last_at = events[0][0], events[-1][0]
    assert first_at < STALL_SECONDS / 2, (
        f"first event took {first_at:.2f}s, so the endpoint waited for the whole "
        "review before sending anything - it is buffering, not streaming"
    )
    assert last_at - first_at > STALL_SECONDS / 2, (
        f"all events arrived within {last_at - first_at:.2f}s of each other despite a "
        f"{STALL_SECONDS}s stall mid-review - they were buffered and flushed together"
    )


def test_done_is_the_final_event_and_the_stream_closes(server):
    def fake_stream(source_code, language="python", force_full_audit=False, repo_id=""):
        yield "progress", {"node": "supervisor", "label": "routing", "elapsed_ms": 1}
        yield "progress", {"node": "collect", "label": "collecting", "elapsed_ms": 2}
        yield "done", _blank_state(language)

    assert [name for _, name in server(fake_stream)] == ["progress", "progress", "done"]


def test_a_mid_stream_failure_becomes_an_error_event_not_a_500(server):
    """Once the response has started the status code is already sent, so the
    only way left to tell the client is an event."""
    def fake_stream(source_code, language="python", force_full_audit=False, repo_id=""):
        yield "progress", {"node": "supervisor", "label": "routing", "elapsed_ms": 1}
        raise RuntimeError("model went away")

    assert [name for _, name in server(fake_stream)] == ["progress", "error"]
