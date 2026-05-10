# Smart Task Tracker - AI Middleware Backend

Backend-first orchestration platform where an LLM plans actions and the server enforces validation, authorization, execution, and audit logging.

Source of truth for architecture and roadmap: `project.md`.

## What this backend does

- JWT-authenticated task operations
- Natural-language orchestration endpoint (`POST /chat`)
- Strict planner output validation before execution
- Policy/authorization checks before tool execution
- Audit log persistence for orchestration requests
- Insights endpoints (priority, productivity, anomalies, next actions, outcomes)
- Background daily summary scheduler

This repository intentionally supports channel integrations (Slack/email/API clients). A frontend is out of scope for the roadmap.

## Stack (current)

- FastAPI + SQLAlchemy
- SQLite (current local DB), designed to migrate toward PostgreSQL
- OpenAI API (planner + AI routes)

## Run locally

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
set DEMO_MODE=true
set OPENAI_API_KEY=your_key_here
set OPENAI_MODEL=gpt-4o-mini
uvicorn app.main:app --reload
```

### Slack `/slack/events` (optional)

For production-like requests you must set **`SLACK_SIGNING_SECRET`** and send valid `X-Slack-Request-Timestamp` / `X-Slack-Signature` headers (see Slack Events API docs).

For **local smoke tests only**, you can disable signature verification:

```bash
set SLACK_SKIP_SIGNATURE_VERIFY=true
```

Never enable **`SLACK_SKIP_SIGNATURE_VERIFY`** in production.

Ensure the Slack user exists on `users.slack_user_id` for your test payloads (map a Slack member ID to an internal user in the DB). Requires **`OPENAI_API_KEY`** for the planner step.

Example URL verification (no signature headers needed when skip is on):

**PowerShell** — `curl` is an alias for `Invoke-WebRequest`, so use **`Invoke-RestMethod`** or **`curl.exe`** (real curl):

```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8000/slack/events" -Method POST -ContentType "application/json" -Body '{"type":"url_verification","challenge":"hello"}'
```

```powershell
curl.exe -s -X POST http://127.0.0.1:8000/slack/events -H "Content-Type: application/json" -d "{\"type\":\"url_verification\",\"challenge\":\"hello\"}"
```

**Git Bash / WSL / macOS / Linux:**

```bash
curl -s -X POST http://127.0.0.1:8000/slack/events -H "Content-Type: application/json" -d '{"type":"url_verification","challenge":"hello"}'
```

Optional: **`REDIS_URL`** enables Redis on app startup (request counters on `/chat` when configured).

API:

- `http://127.0.0.1:8000`
- Swagger docs: `http://127.0.0.1:8000/docs`

## Core orchestration endpoints

- `POST /chat` - natural-language request -> planner -> validator -> authz -> execution
- `POST /clarify` - clarification loop response intake
- `GET /audit/{id}` - fetch orchestration audit record

Supporting domain endpoints remain available under:

- `/tasks`
- `/summary`
- `/insights`
- `/analytics`
- `/demo`
- `/ai`

## Demo account (optional)

- email: `demo@smarttracker.local`
- password: `demo1234`

`DEMO_MODE=true` enables demo-only flows.
