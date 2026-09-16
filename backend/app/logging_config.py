"""Structured (JSON-lines) logging.

Plain-text logs (``"%(asctime)s %(levelname)s %(message)s"``, the previous
default) read fine in a terminal and are close to useless in any real log
aggregator — Loki, CloudWatch, whatever Render's own log viewer forwards to —
because there is nothing to filter or group on except substring search. One
JSON object per line, stdlib only (no `structlog`/`python-json-logger`
dependency for what a `logging.Formatter` subclass already does), fixes that
without changing a single one of the `logger.info(...)` call sites already
in main.py and pr_bot.py.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

# Attributes a LogRecord carries that are implementation detail, not useful in
# an aggregator — everything else on the record (including `exc_info`, handled
# separately below, and any extra=... fields a caller passed) gets emitted.
_STANDARD_RECORD_ATTRS = frozenset(logging.LogRecord("", 0, "", 0, "", (), None).__dict__)


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        # Anything passed via logging's own `extra={...}` - e.g. a request id
        # or a review's routed-to list - rides through untouched rather than
        # being swallowed, which plain %-formatting would do silently.
        for key, value in record.__dict__.items():
            if key not in _STANDARD_RECORD_ATTRS and key not in payload:
                payload[key] = value

        return json.dumps(payload, default=str)


def configure_json_logging(level: int = logging.INFO) -> None:
    """Route the root logger through :class:`JsonFormatter`.

    Called once, at import time in main.py, before any module-level
    ``logging.getLogger(...)`` calls elsewhere in the app do their first
    logging — those calls only need a name; the handler and format are a
    root-logger concern and stay in exactly one place.
    """
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())

    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)
