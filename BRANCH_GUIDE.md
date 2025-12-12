# Branch Switching Guide

## Quick Reference

| Branch | Framework | Status | Use Case |
|--------|-----------|--------|----------|
| `main` | LangGraph + OpenAI | ✅ Stable | Production-ready, custom control |
| `feature/vanna2.0` | Vanna 2.0 Agent | 🚧 Experimental | Tool Memory, simpler code |

## Switch to Main Branch

```bash
# Switch to main
git checkout main

# Verify you're on main
git branch

# Install dependencies (if different)
pip install -r requirements.txt

# Run server
python manage.py runserver 8000

# Test endpoint
curl -X POST http://localhost:8000/api/agents/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "Find 2 bedroom apartments"}'
```

## Switch to Vanna 2.0 Branch

```bash
# Switch to feature branch
git checkout feature/vanna2.0

# Verify you're on the right branch
git branch

# Install Vanna 2.0 dependencies
pip install "vanna[openai,fastapi]>=2.0.0"

# Run server
python manage.py runserver 8000

# Test Vanna endpoint
curl -X POST http://localhost:8000/api/vanna/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "Find 2 bedroom apartments"}'
```

## View Branches

```bash
# List all branches
git branch -a

# Show current branch
git branch --show-current

# View commit differences
git log main..feature/vanna2.0 --oneline
```

## Compare Approaches

### Run Side-by-Side Test

```bash
# Terminal 1: Main branch
git checkout main
python manage.py runserver 8000

# Terminal 2: Test main
curl -X POST http://localhost:8000/api/agents/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "Find luxury apartments in Dubai"}'

# Then switch
git checkout feature/vanna2.0
python manage.py runserver 8000

# Terminal 2: Test Vanna
curl -X POST http://localhost:8000/api/vanna/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "Find luxury apartments in Dubai"}'
```

## Merge Feature Branch (After Testing)

```bash
# If Vanna 2.0 performs better, merge to main
git checkout main
git merge feature/vanna2.0

# Resolve any conflicts
# Then commit
git commit -m "Merge Vanna 2.0 implementation"
```

## Keep Both (Recommended for Now)

For now, **keep both branches** to compare:

1. **main** - Stable, production-ready
2. **feature/vanna2.0** - Experimental, better Tool Memory

Test both thoroughly before deciding which to use in production!

---

**Current Branch:**
```bash
git branch --show-current
```
