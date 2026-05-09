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
