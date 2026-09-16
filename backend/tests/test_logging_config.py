"""``JsonFormatter`` — the one thing worth testing about structured logging is
that it actually produces valid, parseable JSON with the fields an
aggregator would filter on, and that it doesn't silently drop extras or
swallow an exception traceback."""

import json
import logging

from app.logging_config import JsonFormatter


def _make_record(msg="hello", level=logging.INFO, exc_info=None, extra=None) -> logging.LogRecord:
    record = logging.LogRecord(
        name="code_guardian.test",
        level=level,
        pathname=__file__,
        lineno=1,
        msg=msg,
        args=(),
        exc_info=exc_info,
    )
    for key, value in (extra or {}).items():
        setattr(record, key, value)
    return record


def test_output_is_valid_json_with_the_core_fields():
    line = JsonFormatter().format(_make_record("review started"))
    payload = json.loads(line)  # raises if this isn't valid JSON

    assert payload["message"] == "review started"
    assert payload["level"] == "INFO"
    assert payload["logger"] == "code_guardian.test"
    assert "timestamp" in payload


def test_extra_fields_ride_through_rather_than_being_dropped():
    line = JsonFormatter().format(
        _make_record("webhook rejected", extra={"repo": "acme/widgets", "reason": "bad signature"})
    )
    payload = json.loads(line)

    assert payload["repo"] == "acme/widgets"
    assert payload["reason"] == "bad signature"


def test_exception_info_is_included_when_present():
    try:
        raise ValueError("boom")
    except ValueError:
        import sys

        record = _make_record("review failed", level=logging.ERROR, exc_info=sys.exc_info())

    payload = json.loads(JsonFormatter().format(record))
    assert "ValueError: boom" in payload["exception"]


def test_no_exception_key_when_there_is_no_exception():
    payload = json.loads(JsonFormatter().format(_make_record("clean pass")))
    assert "exception" not in payload
