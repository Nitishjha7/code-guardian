# Setup Guide

This covers getting the repo running. If you only want to start the app, the
[Quick start in the README](../README.md#quick-start) is enough — this doc goes
further: local development without Docker, the git remote, and a troubleshooting
table.

> **Note:** an earlier version of this file described *creating* the scaffold
> (`mkdir`, `touch` for empty files). That is no longer relevant — the code is
> written. The scaffold history is in git.

## Prerequisites

| Requirement | Why |
|---|---|
| Docker + Docker Compose | the simplest path — both services with one command |
| Groq API key | the agents run on it — https://console.groq.com/keys (free) |
| Python 3.11+ | only if running the backend without Docker |
| Node 20+ | only if running the frontend without Docker |

## Step 1: Clone

```bash
git clone git@github.com:Nitishjha7/code-guardian.git
cd code-guardian
```

## Step 2: Create the environment file

```bash
cp backend/.env.example backend/.env
```

Then put your key in `backend/.env`:

```
GROQ_API_KEY=gsk_...
```

No spaces around `=`, no quotes, and **save the file**. `.env` is gitignored, so
the key is never committed.

## Step 3: Verify the model id

Groq retires model ids over time. Before running, check that the configured model
is one your key can actually see:

```bash
curl https://api.groq.com/openai/v1/models \
  -H "Authorization: Bearer $GROQ_API_KEY"
```

The default is `openai/gpt-oss-120b`. **The model must support tool calling** —
the supervisor depends on it. If the default is not in the list, set any
tool-calling model in `GUARDIAN_MODEL`.

## Step 4: Run

```bash
docker compose up --build
```

- UI → http://localhost:3000
- API → http://localhost:8010/api/health

The health response should show `"groq_key_configured": true`. If it shows
`false`, revisit Step 2.

## Local development (without Docker)

```bash
# Terminal 1 — backend
cd backend
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000

# Terminal 2 — frontend
cd frontend
npm install
npm run dev                        # http://localhost:5173
```

The Vite dev server proxies `/api` to `localhost:8000` (where the backend runs in
this flow; under Compose the host port is 8010), so `frontend/.env` needs no
changes.

## Tests and eval

```bash
# 107 unit tests — no API key needed
cd backend && pytest -q

# Routing eval — needs an API key (~40 LLM calls for both sets)
cd backend && python -m evals.run_routing_eval --set both
```

No local Python? Use Docker:

```bash
docker build -f backend/Dockerfile.test -t cg-test backend && docker run --rm cg-test
docker build -f backend/Dockerfile.eval -t cg-eval backend && docker run --rm --env-file backend/.env cg-eval
```

## Git remote

```bash
git remote -v
# origin  git@github.com:Nitishjha7/code-guardian.git
```

If SSH is not set up on a new machine, switch to HTTPS:

```bash
git remote set-url origin https://github.com/Nitishjha7/code-guardian.git
```

## Troubleshooting

| Problem | Cause / fix |
|---|---|
| `port is already allocated` | 8000 or 3000 is busy on the host. Change the host side in `docker-compose.yml` (the backend is already on `8010:8000`). |
| `/api/review` → **503** | `GROQ_API_KEY` is not set. |
| `/api/review` → **502** | The key was rejected — wrong or expired. |
| `/api/review` → **429** | Groq rate limit. The free tier is 200k tokens/day per model; try a smaller model or wait for the reset. |
| Review shows an "audit failed" banner | The model id is wrong or retired. Run Step 3. |
| `/webhook/github` → **503** | `GITHUB_WEBHOOK_SECRET` is not set. This is deliberate — the webhook fails closed. |
| `/webhook/github` → **401** | Signature mismatch — GitHub and `.env` must hold the same secret. |
| Frontend says "backend unreachable" | The backend is down, or its origin is missing from `GUARDIAN_CORS_ORIGINS`. |

## Next

- [Project Walkthrough](PROJECT_WALKTHROUGH.md) — the whole system in one file
- [Technical Specification](TECHNICAL_SPEC.md) — architecture and graph topology
- [Build & Deploy Guide](BUILD_AND_DEPLOY.md) — deployment and interview prep
