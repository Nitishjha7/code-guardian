FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /srv

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY logging.json .

# Non-root: nothing here needs to write to the filesystem.
RUN useradd --create-home --uid 10001 guardian
USER guardian

EXPOSE 8000

# --log-config matters here, not just app/logging_config.py's own root-logger
# setup: uvicorn calls its own logging.config.dictConfig() at server startup,
# which runs after this app is imported and re-points uvicorn/uvicorn.access
# at plain-text handlers regardless of what configure_json_logging() already
# did to root. Without this flag, /api/review's own logs are correctly JSON
# and every access-log line (path, status, latency) stays plain text - a real
# gap in what "structured logging" claims, found by actually looking at the
# container's stdout rather than trusting the formatter alone.
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --log-config logging.json"]
