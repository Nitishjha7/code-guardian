FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /srv

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY logging.json .

# Non-root. /data is the one writable path, for app/memory/store.py's SQLite
# file (MEMORY_DB_PATH); the rest of the image is read-only to this user.
RUN useradd --create-home --uid 10001 guardian \
    && mkdir -p /data && chown guardian:guardian /data
USER guardian

EXPOSE 8000

# --log-config is required, not redundant with app/logging_config.py: uvicorn
# runs its own dictConfig() at startup, after the app is imported, and re-points
# uvicorn.access at plain-text handlers. Without the flag the access logs stay
# unstructured while the app's own logs are JSON.
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --log-config logging.json"]
