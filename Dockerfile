# Single-service deploy image: FastAPI serves the API and the built React app
# from one origin, so there is no CORS to configure and one service to deploy.
# docker-compose uses backend/Dockerfile and frontend/Dockerfile instead.
#
# Build from the repo root: docker build -f Dockerfile .

# ---- stage 1: build the React app ----
FROM node:20-alpine AS frontend

WORKDIR /fe

COPY frontend/package.json frontend/package-lock.json* ./
RUN npm ci

COPY frontend/ ./
# VITE_API_URL is left unset so api.js falls back to "/api" — on this image that
# is the same service. Baking in an absolute URL is what makes the frontend
# build and the backend deploy drift apart.
RUN npm run build

# ---- stage 2: python app + static files ----
FROM python:3.11-slim

WORKDIR /app

COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/app ./app
COPY backend/logging.json .
COPY --from=frontend /fe/dist ./static

EXPOSE 8000

# --log-config is required, not redundant with app/logging_config.py: uvicorn
# runs its own dictConfig() at startup, after the app is imported, and re-points
# uvicorn.access at plain-text handlers. Without the flag the access logs stay
# unstructured while the app's own logs are JSON.
#
# Shell form so $PORT expands; the default keeps plain `docker run` working.
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --log-config logging.json"]
