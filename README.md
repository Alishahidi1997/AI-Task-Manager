# Smart Task Tracker

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
- Async-ready design prepared for queues and worker-based scaling

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
- Database: SQLite (extendable to PostgreSQL)
- AI: OpenAI tool calling (optional via API key)
- Async: Background tasks (queue-ready design)
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

- Productivity tracking (completion patterns, delays)
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
- Built with production failure modes in mind

---

## Phase 2 (implementation roadmap)

Cursor-executable **Epics 1–4** with acceptance criteria, file targets, and Composer prompts live in **`project.md` → Phase 2: Production-Ready**.

| Epic | Focus |
| --- | --- |
| 1 | PostgreSQL + Alembic, RabbitMQ workers, Redis rate limit / cache |
| 2 | `ThreadManager` (context drift), entity resolution for assignees/tasks |
| 3 | Semantic policy engine, unified AI audit trail |
| 4 | `tests/evals` golden set, tool/parameter accuracy benchmarks in CI |

**Done:** pytest integration tests (`python -m pytest`).

---

## Setup

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

API docs: http://127.0.0.1:8000/docs

### Tests

Uses a temporary SQLite file (`DATABASE_URL`), not your dev `db.sqlite3`. Scheduler is off; Slack signature check is skipped.

```bash
python -m pytest
```

Covers health, auth, task CRUD, Slack URL verification + unmapped user, and `/chat` with a mocked planner (no OpenAI key required).