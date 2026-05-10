# Backend Workflow Reference

This document is aligned to the backend-only architecture in `project.md`.

`project.md` is the source of truth for implementation scope, layering, and roadmap.

---

## Implementation posture (junior+ / early mid)

This project is intentionally implemented at a **junior+ to early mid** architecture level: **solid fundamentals** (clear layering, validation before execution, audit trails, shared resources via FastAPI lifespan / `Depends`), **pragmatic** use of middleware and optional infrastructure (logging, Redis when configured, streaming where it helps UX), and **readable code paths** that a teammate can follow without a map.

That posture explicitly **avoids** premature complexity—extra abstraction layers “because enterprise,” unused patterns, or splitting into many tiny services before there is a concrete need. When trade-offs appear, prefer **clarity and maintainability** over cleverness, and grow structure only when the codebase proves it needs it.

---

## 1. System scope

- Backend orchestration platform only.
- Client channels can be Slack, email, API consumers, or internal services.
- LLM is a planner, not an executor.
- Trusted backend layers validate, authorize, execute, and audit every action.

---

## 2. Current codebase layout (as-is)

| Area | Role |
|------|------|
| `app/main.py` | FastAPI app, lifespan startup/shutdown. |
| `app/database.py` | DB session and migration helper. |
| `app/models.py` | ORM models. |
| `app/routes/*.py` | API endpoints and route-level checks. |
| `app/services/*.py` | Domain logic and planner support logic. |
| `app/scheduler.py` | Background summary scheduler. |

Target production structure and services are defined in `project.md` section 4 and section 15.

---

## 3. Server startup workflow (lifespan)

When Uvicorn loads `app.main:app`, the **lifespan** context runs once before requests are served.

1. **Tables**: `Base.metadata.create_all` ensures ORM tables exist.
2. **SQLite patches**: `migrate_sqlite(engine)` adds missing columns on existing DBs (e.g. `user_id`, `category`, `completed_at` on tasks; `user_id` on summaries) and backfills legacy data.
3. **Demo user**: Ensures `demo@smarttracker.local` exists with a known password hash (see `README.md` for the password).
4. **Data hygiene**:
   - Tasks with `user_id` NULL are assigned to the demo user.
   - Tasks with `category` NULL get `guess_category(...)` applied and persisted.
5. **Empty demo DB**: If the demo user has zero tasks, `reset_demo_dataset` seeds demo tasks.
6. **Scheduler**: `start_scheduler()` starts APScheduler.
7. On shutdown, the scheduler stops.

**Important**: Startup does not run the full app logic for every request; it only prepares the database and background jobs.

---

## 4. Background scheduler workflow

File: `app/scheduler.py`.

- Default: a **cron** job runs at **00:00** (server local timezone of the scheduler) with id `daily-summary`.
- Override for testing: set `SUMMARY_EVERY_MINUTES=<positive integer>` to run the same job on that interval instead of daily midnight.

Each run:

1. Opens a DB session.
2. Iterates **all users**.
3. For each user, loads recent **done** tasks (up to 50), calls `build_daily_summary`, writes a `DailySummary` row (`is_error=0` on success).
4. On failure, rolls back the failed attempt, writes an error row (`is_error=1`) so you can see failures in the DB.

This is separate from the **on-demand** `/summary/daily` route (see below), which may return the latest stored summary or generate one when appropriate.

---

## 5. Data model workflow

### User (`users`)

- `email` (unique), `password_hash`, `created_at`.
- Created via `/auth/register` or ensured at startup for the demo email.

### Task (`tasks`)

- Core fields: `title`, `description`, `status`, `due_date`, `category`, `created_at`, `completed_at`, `user_id`.
- **Status workflow** (enforced on update in `app/routes/tasks.py`):
  - `todo` → `todo`, `in_progress`
  - `in_progress` → `in_progress`, `done`, `todo`
  - `done` → `done`, `in_progress` (reopen)
- When a task becomes **done**, `completed_at` is set; when leaving `done`, it is cleared. This feeds productivity and playback metrics.

### DailySummary (`daily_summaries`)

- Stores generated summary text, `mode` (e.g. OpenAI vs fallback), `task_count`, `user_id`, `created_at`, `is_error`.

---

## 3. Runtime request pipeline

1. Receive natural language request from channel/API.
2. Authenticate and resolve identity context.
3. Build planner prompt with allowed tools + schema.
4. LLM returns strict JSON tool call.
5. Validate structured output.
6. Enforce policy and authorization.
7. Execute backend action with trusted services.
8. Persist data and write audit logs.
9. Return result or clarification request.

---

## 4. HTTP API workflow (current implementation)

All paths below are relative to the API root (e.g. `http://127.0.0.1:8000`). Protected routes expect a JWT unless noted.

### Auth (`/auth`)

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/auth/register` | Create user, return JWT + user info. |
| POST | `/auth/login` | Return JWT + user info. |
| GET | `/auth/me` | Return current user from JWT. |

Clients pass bearer tokens; channel adapters should inject and map identity into this API.

### Tasks (`/tasks`)

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/tasks` | Create task; category defaults via `guess_category` if omitted. |
| GET | `/tasks` | List current user’s tasks; optional `status`, `due_before`, `due_after`. |
| GET | `/tasks/{id}` | Single task. |
| PUT | `/tasks/{id}` | Partial update; status transitions validated; `completed_at` maintained. |
| DELETE | `/tasks/{id}` | Delete. |

### Summary (`/summary`)

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/summary/daily` | Returns latest successful `DailySummary` for the user, or generates and stores one from recent done tasks when none suitable exists. |
| GET | `/summary/weekly-retro` | Computes a structured weekly retro from done + open tasks (no separate weekly table required). |

### Insights (`/insights`)

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/insights/productivity` | Bucketed completion speed from done tasks with timestamps. |
| GET | `/insights/priority` | Overdue open tasks, sorted and narrated. |
| GET | `/insights/explain/{insight_id}` | Deeper “why” for supported insight ids (e.g. `productivity`, `priority`). |
| GET | `/insights/anomalies` | KPI anomaly detection over daily buckets; query `days`, `baseline_days`. |

### Analytics (`/analytics`)

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/analytics/playback` | Daily time series for completion count, overdue count, and average cycle time for tasks completed that day (`from`, `to`, `step=day`). |

### Demo (`/demo`) — gated

Requires:

- Environment: `DEMO_MODE=true`
- Authenticated user email exactly `demo@smarttracker.local`

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/demo/scenarios` | List named demo datasets. |
| POST | `/demo/load/{scenario_id}` | Replace demo tasks with that scenario. |
| POST | `/demo/reset` | Reset demo tasks to baseline seed. |

### AI (`/ai`)

Protected routes that use OpenAI when configured (see route implementations and `app/services/*`). Typical uses: natural language task parse, roadmap planning, agent-style commands with tool calls. The frontend exposes these in the composer and “AI Command Console”.

### Slack (`/slack`)

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/slack/events` | Slack Events API: verifies Slack signing secret (unless dev bypass env), normalizes event, maps Slack user → internal user, planner → structured validation → policy → **trusted execution** (`app/services/slack_execution.py`) → `audit_logs` row. Returns JSON including `status`: `executed`, `clarification_required`, `policy_rejected`, `execution_failed`, etc., and `audit_id` when an audit row was written. |

Execution respects tenant isolation by scoping task queries to `user_id`. Assignee on tasks is persisted via `description` lines (`Assignee: …`) because the MVP task schema does not include a dedicated assignee column.

---

## 7. Category (“smart grouping”) workflow

- On **create**, if `category` is omitted, `guess_category(title, description, due_date)` runs.
- On **startup**, any NULL `category` is backfilled the same way.
- Buckets are the planning labels used across insights (e.g. `today`, `this_week`, `routine`, `backlog` — exact set is defined in code/schemas).

---

## 5. End-to-end backend journeys

### New developer

1. Create venv, `pip install -r requirements.txt`.
2. Set optional env vars (`OPENAI_API_KEY`, `DEMO_MODE`, `SUMMARY_EVERY_MINUTES`).
3. Run `uvicorn app.main:app --reload`.
4. In `frontend/`, `npm install`, configure `.env` from `.env.example`, `npm run dev`.
5. Open Swagger at `/docs` to probe routes with a token from `/auth/login`.

### End user/channel task loop

1. Register or log in.
2. Submit natural-language requests to the orchestration endpoint.
3. Planner produces tool call; backend validates and authorizes.
4. Execution service applies changes and stores outcomes/audit logs.
5. Channel receives confirmation or clarification prompt.

### Demo presenter

1. Backend with `DEMO_MODE=true`.
2. Log in as `demo@smarttracker.local`.
3. Load scenarios or reset to baseline to tell a consistent story.

---

## 6. Environment variables (reference)

| Variable | Effect |
|----------|--------|
| `OPENAI_API_KEY` | Enables OpenAI-backed summaries and AI routes where implemented. |
| `OPENAI_MODEL` | Model name for OpenAI calls (see `README.md`). |
| `DEMO_MODE` | Must be `true` for demo-only `/demo/*` routes for the demo user. |
| `SUMMARY_EVERY_MINUTES` | If set to a positive integer, scheduler runs the summary job that often instead of daily midnight. |

---

## 7. Where to extend next

Follow `project.md` only. It now defines backend-only production architecture, interfaces, and safety requirements.

---

## 8. Quick diagram (request path)

```text
Channel Client (Slack / Email / API)
    |  auth context + request
    v
FastAPI (CORS)
    |-- auth: JWT/OAuth -> Identity
    v
Route handler / Orchestrator
    v
SQLAlchemy Session -> SQLite (db.sqlite3)
    |
    +--> validator + policy + execution services
    |
    +--> audit logs + scheduler side jobs
```

That is the full loop: **identity -> planning -> validation -> authorization -> execution -> persistence/audit -> response**.
