# Code Guardian — Setup Guide

Ye guide repo ko chalane ke liye hai. Agar sirf app run karna hai toh
[README ka Quick start](../README.md#quick-start) kaafi hai — ye doc us se aage
ki cheezein cover karta hai (local dev without Docker, git remote, common issues).

> **Note:** is doc ka purana version project ka *scaffold banane* ke steps deta
> tha (`mkdir`, `touch` se khaali files). Wo ab relevant nahi hai — code likha
> ja chuka hai. Scaffold history git me hai.

## Prerequisites

| Cheez | Kyun chahiye |
|---|---|
| Docker + Docker Compose | sabse aasan raasta — dono services ek command me |
| Groq API key | agents isi pe chalte hain — https://console.groq.com/keys (free) |
| Python 3.11+ | sirf agar Docker ke bina backend chalana ho |
| Node 20+ | sirf agar Docker ke bina frontend chalana ho |

## Step 1: Repo clone karo

```bash
git clone git@github.com:Nitishjha7/code-guardian.git
cd code-guardian
```

## Step 2: Environment file banao

```bash
cp backend/.env.example backend/.env
```

Phir `backend/.env` me apni key daalo:

```
GROQ_API_KEY=gsk_...
```

**Dhyan rakhna:** `=` ke aaspaas space nahi, quotes nahi, aur file **save**
zaroor karo. `.env` gitignored hai — key kabhi commit nahi hogi.

## Step 3: Model id verify karo

Groq purane model ids retire karta rehta hai. Chalane se pehle check kar lo ki
jo model set hai wo tumhari key ko dikhta hai:

```bash
curl https://api.groq.com/openai/v1/models \
  -H "Authorization: Bearer $GROQ_API_KEY"
```

Default `openai/gpt-oss-120b` hai. **Model tool calling support karta ho ye
zaroori hai** — supervisor usi pe chalta hai. Agar list me na mile toh koi aur
tool-calling model `GUARDIAN_MODEL` me daal do.

## Step 4: Chalao

```bash
docker compose up --build
```

- UI → http://localhost:3000
- API → http://localhost:8010/api/health

Health response me `"groq_key_configured": true` dikhna chahiye. `false` hai toh
Step 2 dobara dekho.

## Local dev (Docker ke bina)

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

Vite dev server `/api` ko `localhost:8000` pe proxy karta hai (Docker ke bina wale flow me backend wahin chalta hai; compose me host port 8010 hai), isliye
`frontend/.env` chhedne ki zaroorat nahi.

## Tests aur eval

```bash
# 71 unit tests — koi API key nahi chahiye
cd backend && pytest -q

# Routing eval — API key chahiye (~20 LLM calls)
cd backend && python -m evals.run_routing_eval
```

Local Python nahi hai? Docker se:

```bash
docker build -f backend/Dockerfile.test -t cg-test backend && docker run --rm cg-test
docker build -f backend/Dockerfile.eval -t cg-eval backend && docker run --rm --env-file backend/.env cg-eval
```

## Git remote

```bash
git remote -v
# origin  git@github.com:Nitishjha7/code-guardian.git
```

Agar naye machine pe SSH set nahi hai toh HTTPS use karo:

```bash
git remote set-url origin https://github.com/Nitishjha7/code-guardian.git
```

## Common issues

| Problem | Wajah / fix |
|---|---|
| `port is already allocated` | Host pe 8000/3000 busy hai. `docker-compose.yml` me host-side port badlo (backend already `8010:8000` pe hai). |
| `/api/review` → **503** | `GROQ_API_KEY` set nahi hai. |
| `/api/review` → **502** | Key reject ho gayi — galat ya expire. |
| `/api/review` → **429** | Groq rate limit. Thodi der baad retry. |
| Review me "audit failed" banner | Model id galat/dead hai. Step 3 chalao. |
| `/webhook/github` → **503** | `GITHUB_WEBHOOK_SECRET` set nahi. Ye jaan-boojh ke fail-closed hai. |
| `/webhook/github` → **401** | Signature match nahi hui — GitHub aur `.env` ka secret same hona chahiye. |
| Frontend "backend unreachable" | Backend up nahi hai, ya CORS origin `GUARDIAN_CORS_ORIGINS` me nahi hai. |

## Aage kya

- [Technical Specification](TECHNICAL_SPEC.md) — architecture aur graph topology
- [Build & Deploy Guide](BUILD_AND_DEPLOY.md) — deployment + interview prep
