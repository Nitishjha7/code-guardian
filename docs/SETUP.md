# Code Guardian — Setup Guide

## Step 1: Naya folder + git init
```bash
cd ~/Music
mkdir code-guardian
cd code-guardian
git init
```

## Step 2: Folder structure banao
```bash
mkdir -p backend/app/agents
mkdir -p backend/app/mcp_clients
mkdir -p backend/app/guardrails_config
mkdir -p frontend/src

touch backend/requirements.txt
touch backend/Dockerfile
touch backend/app/__init__.py
touch backend/app/graph.py
touch backend/app/agents/security_agent.py
touch backend/app/agents/performance_agent.py
touch backend/app/agents/patch_generator.py
touch backend/app/agents/supervisor.py
touch frontend/Dockerfile
touch docker-compose.yml
touch README.md
touch .gitignore
```

## Step 3: .gitignore banao
```bash
cat > .gitignore << 'EOF'
venv/
__pycache__/
*.pyc
node_modules/
dist/
.env
*.db
*.log
EOF
```

## Step 4: README likho
```bash
echo "# Code Guardian — Multi-Agent Autonomous Code Reviewer & PR Bot" > README.md
```

## Step 5: Git config check (agar already set nahi hai)
```bash
git config user.email nitishkj5019@gmail.com
```

## Step 6: Main branch + pehla commit
```bash
git branch -M main
git add .
git commit -m "Initial project scaffold - Code Guardian"
```

## Step 7: GitHub pe naya repo banao

Browser me jaake GitHub pe naya repo banao naam se `code-guardian` (empty rakhna — bina README/gitignore, kyunki tumhare paas already hai).

## Step 8: Remote add karo aur push karo
```bash
git remote add origin git@github-personal:Nitishjha7/code-guardian.git
git push -u origin main
```
