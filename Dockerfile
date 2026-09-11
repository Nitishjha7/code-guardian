# Single-service deploy image: FastAPI serves both the API and the built React app.
#
# Why one container instead of two: a split deployment needs CORS configured, a
# second service to deploy, and a second thing to keep awake. Serving the SPA
# from the same origin removes all three — `VITE_API_URL` stays at its `/api`
# default and there is no cross-origin request to allow.
#
# `backend/Dockerfile` and `frontend/Dockerfile` still exist and are what
# docker-compose uses locally, where nginx serves the frontend separately.
#
# Build context is the repo root:  docker build -f Dockerfile .

# ---- stage 1: build the React app ----
FROM node:20-alpine AS frontend

WORKDIR /fe

COPY frontend/package.json frontend/package-lock.json* ./
RUN npm ci

COPY frontend/ ./
# Left unset on purpose: api.js falls back to "/api", which on this image is
# this same service. Baking an absolute URL here is what makes a frontend build
# and a backend deploy drift apart.
RUN npm run build

# ---- stage 2: python app + static files ----
FROM python:3.11-slim

WORKDIR /app

# git is not needed at runtime, but Bandit's dependency chain is lighter to
# install with build essentials absent — keep the image to what actually runs.
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/app ./app
COPY --from=frontend /fe/dist ./static

EXPOSE 8000

# Render and most PaaS inject the port to bind as $PORT. Shell form so it
# expands; the default keeps plain `docker run` working locally.
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
