# Smart Task Tracker

[![CI](https://github.com/Alishahidi1997/AI-Task-Manager/actions/workflows/ci.yml/badge.svg)](https://github.com/Alishahidi1997/AI-Task-Manager/actions/workflows/ci.yml)

A production-style backend system that enables natural language task management while enforcing strict server-side validation, policy control, and full auditability.

The LLM acts only as a planner. It suggests structured tool calls, while the backend validates, authorizes, executes, and logs all operations.

---

## Key Features

- Natural language to structured task execution using LLM tool calling
- Server-side validation and policy enforcement (no direct LLM writes to database)
- Role-based access control (employee, manager, admin)
- Full audit logging of all AI-driven actions
- Hybrid architecture combining REST API, AI orchestration, and Slack integration
- Insights engine for productivity, priorities, and anomalies
- RabbitMQ-backed LLM orchestration workers (`/chat`, Slack, `/ai/*`, daily summaries)

---

## Architecture

User Input (REST / Slack / Chat)
→ LLM Planner (tool suggestions only)
→ Validation Layer (schema validation + policy checks)
→ Execution Engine (safe database operations)
→ Audit Logger
→ Response (API or Slack reply)

Core principle:
The model suggests, the system decides.

---

## Tech Stack

- Backend: FastAPI (Python)
- Frontend: React (optional UI)
- Authentication: JWT
- Database: SQLite (local) or PostgreSQL + Alembic (production-shaped)
- AI: OpenAI tool calling (optional via API key)
- Async: RabbitMQ workers for LLM orchestration and batch jobs
- Integrations: Slack Events API

---

## Core Modules

### Task System (REST API)

- Create, read, update, delete tasks
- Filtering by status, due date, and priority
- Enforced ownership and permission rules in backend

---

### LLM Orchestration (/chat)

- Converts natural language into structured tool calls
- Validates and executes only allowed actions
- Handles clarification flows when needed
- Returns structured responses with audit IDs

---

### Slack Integration

- Real-time Slack event processing
- Request signature verification for security
- Role-based tool exposure per user
- Full traceability for every Slack interaction

---

### Insights Engine

- Productivity tracking (completion patterns, delays)c
- Priority analysis (overdue and high-risk tasks)
- Anomaly detection across user behavior
- Next-action recommendations

---

### Demo System

- Pre-seeded scenarios for testing and demos
- Role-based dashboards (manager, analyst, executive)
- Resettable environment for presentations

---

## Design Principles

- Zero-trust execution of LLM outputs
- Strict separation of planning and execution
- Full auditability of all AI actions
- Failure-safe design with fallback handling
- Extensible architecture for queues, workers, and microservices

---

## What Makes This System Different

Unlike typical LLM wrapper applications:

- The LLM cannot directly modify data
- Every action is validated before execution
- All AI decisions are logged and traceable
- The system treats AI as a planner, not an executor
- Slack and `/chat` share one planner JSON shape (`tool_name` + `arguments`; legacy `tool` is normalized at validation)
- Built with production failure modes in mind

---

## Phase 2 (implementation roadmap)

All **Epics 1–4** and stretch ops are implemented. Details and acceptance criteria live in **`project.md` → Phase 2: Production-Ready** (local design doc).

| Epic | Status |
| --- | --- |
| 1 | PostgreSQL + Alembic, RabbitMQ LLM queue, Redis rate limits + snapshot cache |
| 2 | `ThreadManager`, entity resolution (task follow-ups, assignee name lookup), Slack thread follow-ups |
| 3 | Semantic policy engine, unified audit dashboard |
| 4 | Golden eval suite (`tests/evals`), accuracy thresholds enforced in **CI** |

**CI:** GitHub Actions runs `python -m pytest` (SQLite + mocked planner evals), Postgres smoke test, RabbitMQ queue delivery test, and Redis rate-limit/cache smoke test. Live OpenAI evals are opt-in: excluded from `ci.yml` via `pytest.ini` (`-m "not live_openai"`); run manually with the **Live planner eval** workflow (`workflow_dispatch`, secret `OPENAI_API_KEY`) or locally with `EVAL_LIVE=1`.

---

## Phase 3 (backlog)

| ID | Item | Status |
| --- | --- | --- |
| 3.1 | Sync design docs with shipped Phase 2 | Partial (see `project.md`; intro updated) |
| 3.2 | Optional live OpenAI eval workflow in CI | **Done** (`.github/workflows/eval-live.yml`, manual dispatch) |
| 3.3 | React `/chat` + queued job/stream UX | **Done** (chat panel; 202 auto-poll via `api.ts`) |
| 3.4 | Redis in CI (rate limits + snapshot cache) | **Done** |
| 3.5 | `Task.assignee` column | **Done** (Alembic `003_assignee`, API + Slack/chat execution) |
| 3.6 | `assign_task` on `/chat` | **Done** (manager/admin; assignee resolution + `Task.assignee`) |
| 3.7 | Production hardening (webhooks, workspace limits, etc.) | Planned |

---

## Setup

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

### One-command local run (Windows)

After first-time setup above (`pip install`, `copy .env.example .env`, `cd frontend && npm install`):

```powershell
.\run-app.ps1           # Docker + API + worker + frontend
.\run-app.ps1 -Simple   # API + frontend only (SQLite)
```

Opens separate PowerShell windows for each service. Requires [Docker Desktop](https://www.docker.com/products/docker-desktop/) for the full stack.

API docs: http://127.0.0.1:8000/docs

### Optional: PostgreSQL (Phase 2 Epic 1.1)

SQLite remains the default for zero-config local dev. For Postgres + Alembic migrations:

```bash
docker compose up -d postgres
export DATABASE_URL=postgresql+psycopg://smarttask:smarttask@localhost:5432/smarttask
alembic upgrade head   # or rely on init_db() at API startup
uvicorn app.main:app --reload
```

Copy `.env.example` to `.env` and adjust. CI/integration: set `POSTGRES_TEST_URL` to the same URL and run `pytest tests/test_postgres.py`.

### Optional: RabbitMQ for LLM orchestration (Phase 2 Epic 1.2)

When `RABBITMQ_URL` is set, `/ai/parse-task`, `/ai/plan-task`, and `/ai/agent-command` return `202` with a `job_id` (batch queue). Poll `GET /jobs/{job_id}` or use the React client (auto-polls on 202).


Offloads `/chat` and async Slack orchestration to a worker so the API does not hold OpenAI connections.

```bash
docker compose up -d rabbitmq
export RABBITMQ_URL=amqp://guest:guest@localhost:5672/
# LLM_QUEUE_ENABLED=true by default when RABBITMQ_URL is set
uvicorn app.main:app --reload
python -m app.worker.main
```

- `POST /chat` → **202** with `job_id`; poll `GET /jobs/{job_id}`
- Slack events → `200` ack + `job_id` when async; worker runs the same orchestration pipeline
- Management UI: http://localhost:15672 (guest/guest)

Without `RABBITMQ_URL`, behavior is unchanged (sync `/chat`, in-process Slack background tasks).

### Optional: Redis rate limits + snapshot cache (Phase 2 Epic 1)

When `REDIS_URL` is set, `/chat`, `/chat/stream`, and Slack message events are rate-limited per user (HTTP **429** with `Retry-After`). `GET /insights/snapshot` is cached briefly (default 60s).

```bash
docker compose up -d redis
export REDIS_URL=redis://localhost:6379/0
uvicorn app.main:app --reload
```

Tune via `.env.example`: `RATE_LIMIT_CHAT_PER_MINUTE`, `RATE_LIMIT_SLACK_PER_MINUTE`, `INSIGHTS_SNAPSHOT_CACHE_SECONDS`. Set `RATE_LIMIT_ENABLED=false` to keep Redis for stats/cache only.

CI: `RUN_REDIS_INTEGRATION=1 REDIS_URL=redis://localhost:6379/0 python -m pytest tests/test_redis_integration.py`

### Tests

Uses a temporary SQLite file (`DATABASE_URL`), not your dev `db.sqlite3`. Scheduler is off; Slack signature check is skipped.

```bash
python -m pytest
```

Covers health, auth, task CRUD, Slack URL verification + unmapped user, `/chat` with a mocked planner, Slack idempotency, status workflow, insights snapshot, and stale-claim reclaim (no OpenAI key required).
