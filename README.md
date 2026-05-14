# Smart Task Tracker

This project is a **FastAPI backend** (plus a small **React** UI in `frontend/`) built around a simple idea: people should be able to talk to software in natural language, but **the server should still own the database**. The model’s job is to pick a structured action and fill in fields; your code checks it, applies policy, runs the real insert/update/delete, and writes an audit row.



## What you need

- **Python 3.10+** (roughly; whatever runs your venv)
- **pip** and a virtualenv
- **Optional:** `OPENAI_API_KEY` if you want summaries, `/chat`, `/ai/*`, or the Slack planner to call OpenAI
- **Optional:** Node.js if you want the React UI

---

## Install and run the API

From the repo root:

```bash
python -m venv .venv
```

Activate the venv:

- **Windows (cmd/PowerShell):** `.venv\Scripts\activate`
- **macOS / Linux:** `source .venv/bin/activate`

Then:

```bash
pip install -r requirements.txt
```

Set env vars (examples below use Windows `set`; on macOS/Linux use `export` instead).

Minimum to boot and use REST + most insights:

```bash
set DEMO_MODE=true
uvicorn app.main:app --reload
```

If you want OpenAI-backed features:

```bash
set OPENAI_API_KEY=sk-...
set OPENAI_MODEL=gpt-4o-mini
```

Open **http://127.0.0.1:8000/docs** — Swagger lists every route and lets you try them after you log in and paste the Bearer token.

---

## Run the React UI (optional)

```bash
cd frontend
npm install
copy .env.example .env
npm run dev
```

Default API URL in `.env.example` is `http://127.0.0.1:8000`. Change `VITE_API_BASE_URL` if your API lives elsewhere.

---

## HTTP endpoints (overview)

Paths are relative to the API root (e.g. `http://127.0.0.1:8000`).

**Auth**

| Method | Path | What it does |
| --- | --- | --- |
| POST | `/auth/register` | Create account, returns JWT |
| POST | `/auth/login` | Returns JWT |
| GET | `/auth/me` | Who am I (needs Bearer token) |

**Tasks (direct REST — no LLM)**

| Method | Path | What it does |
| --- | --- | --- |
| POST | `/tasks` | Create task (body: title, description, due_date, optional category) |
| GET | `/tasks` | List your tasks; query `status`, `due_before`, `due_after` |
| GET | `/tasks/{id}` | One task |
| PUT | `/tasks/{id}` | Update fields / status (workflow rules apply) |
| DELETE | `/tasks/{id}` | Delete |

**Natural language orchestration (LLM in the loop)**

| Method | Path | What it does |
| --- | --- | --- |
| POST | `/chat` | Message in → planner (OpenAI) → validate → policy → execute tool → JSON out + audit id |
| POST | `/chat/stream` | Same idea, streamed response |
| POST | `/clarify` | Answer a clarification the planner asked for |
| GET | `/audit/{id}` | Fetch one orchestration audit row |

**Summaries**

| Method | Path | What it does |
| --- | --- | --- |
| GET | `/summary/daily` | Latest stored daily summary (may generate if needed) |
| GET | `/summary/weekly-retro` | Structured weekly retro from your task data |

**Insights and analytics**

| Method | Path | What it does |
| --- | --- | --- |
| GET | `/insights/snapshot` | One JSON: productivity + priority + anomalies + next-actions digest |
| GET | `/insights/productivity` | Bucketed completion speed |
| GET | `/insights/priority` | Overdue tasks, sorted |
| GET | `/insights/anomalies` | KPI spikes/drops vs baseline (`days`, `baseline_days` query params) |
| GET | `/insights/explain/{insight_id}` | Longer “why” text for supported ids (`productivity`, `priority`, `anomalies`) |
| GET | `/insights/next-actions` | Ranked recovery suggestions on overdue work |
| POST | `/insights/next-actions/outcome` | Record accepted / dismissed / completed |
| POST | `/insights/next-actions/apply` | Apply a suggested change to a task + record outcome |
| GET | `/insights/next-actions/outcomes` | Rollup of feedback over a window |
| GET | `/analytics/playback` | Time series of completions, overdue count, cycle time (`from`, `to`, `step`) |

**AI helpers (OpenAI when key is set)**

| Method | Path | What it does |
| --- | --- | --- |
| POST | `/ai/parse-task` | Turn free text into structured task fields |
| POST | `/ai/plan-task` | Roadmap-style task breakdown |
| POST | `/ai/agent-command` | Agent-style command with tools |

**Demo (only with `DEMO_MODE=true` and the demo email)**

| Method | Path | What it does |
| --- | --- | --- |
| GET | `/demo/scenarios` | List seeded scenarios |
| POST | `/demo/load/{scenario_id}` | Load a scenario |
| POST | `/demo/reset` | Reset demo data |
| GET | `/demo/personas/{role}/dashboard` | Role-shaped dashboard (`manager`, `analyst`, `executive`) |

**Slack**

| Method | Path | What it does |
| --- | --- | --- |
| POST | `/slack/events` | Slack Events API: verify signature, map user, planner, validate, policy, execute, audit, optional bot reply |
| GET | `/slack/traces/{trace_id}` | Fetch orchestration trace for the owning user |

**Misc**

| GET | `/` | Small JSON health check |

---

## Which tools does the LLM get?

There are **two different planners** in this repo. They do not share the exact same tool list.

### 1) Slack (`POST /slack/events`)

After Slack’s request is verified and your internal `User` is found, tools are filtered by **`users.role`** (`employee`, `manager`, `admin`):

| Role | Tools the model may see |
| --- | --- |
| **employee** | `create_task`, `update_task` |
| **manager** | `create_task`, `update_task`, `assign_task`, `delete_task` |
| **admin** | all manager tools plus `admin_tools` |

Registry definitions (what the prompt advertises) live in `app/orchestration/tool_registry.py`:

- **create_task** — required: `assignee`, `title`, `due_date`; optional: `priority`
- **update_task** — required: `task_id`; optional: `status`, `assignee`, `due_date`, `title`, `description`
- **assign_task** — required: `task_id`, `assignee`
- **delete_task** — required: `task_id`
- **admin_tools** — required: `action`; optional: `payload` (in the current codebase this tool is **advertised to the admin role** but **execution raises** — it is not wired to real admin behavior yet)

Execution for Slack is implemented in `app/services/slack_execution.py` (validated arguments only).

### 2) API chat (`POST /chat`, `POST /chat/stream`)

This path uses a **smaller** built-in registry in `app/services/chat_orchestrator.py`:

- **create_task** — required: `title`, `due_date`; optional: `priority`, `assignee`, `description`, `category`
- **update_task** — required: `task_id`; optional: `status`, `assignee`, `due_date`, `title`, `description`
- **delete_task** — required: `task_id`

Authorization there is permission-based (e.g. assignee and high priority gated for non-managers) inside that module — it is **not** identical to the Slack role table above.

---

## Slack env vars (only if you use Slack)

- **`SLACK_SIGNING_SECRET`** — required for real signed requests
- **`SLACK_BOT_TOKEN`** — if you want `chat.postMessage` replies in the thread
- **`SLACK_SKIP_SIGNATURE_VERIFY=true`** — local testing only; never in production
- **`SLACK_EVENTS_ASYNC`** — default `true` (fast ack to Slack); `false` if you want the full JSON in the HTTP response while debugging

---

## Demo account

If `DEMO_MODE=true`:

- **Email:** `demo@smarttracker.local`
- **Password:** `demo1234`

Demo routes and reset/load only work for that account.

---

## Where the architecture is spelled out

See `project.md` in your tree for the long-form design narrative (layers, Slack flow, roadmap). If the file is missing in a fresh clone, check `.gitignore` — some setups ignore it on purpose.
