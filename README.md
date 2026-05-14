# Smart Task Tracker (FastAPI backend)

This repo is a small task API with a few extras: JWT auth, SQLite storage, an optional OpenAI hook for summaries and for the `/chat` tool flow, and a Slack events handler if you want to wire a workspace in.

**the model suggests a tool and arguments; the server decides if that is allowed and then runs the real code.** Nothing hits the database on trust alone.

If you care about the full architecture write-up, it lives in `project.md`. Note: some clones list `project.md` in `.gitignore`, so you might not see it until you add or restore that file locally.

---

## Run it on your machine

Python 3, a venv, then:

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
set DEMO_MODE=true
set OPENAI_API_KEY=your_key_here
set OPENAI_MODEL=gpt-4o-mini
uvicorn app.main:app --reload
```

On macOS/Linux, swap `set` for `export`.

Then open **http://127.0.0.1:8000/docs** — Swagger is the fastest way to try endpoints without writing a client.

There is also a **React UI** under `frontend/` (Vite). It is not the source of truth for the big design doc, but it is handy: `npm install`, copy `frontend/.env.example` to `.env`, `npm run dev`, and point `VITE_API_BASE_URL` at the API if needed.

---

## Slack (completely optional)

If you are not touching Slack, skip this whole section.

For real traffic you need **`SLACK_SIGNING_SECRET`** and Slack's signature headers. For a quick local poke only, some people use **`SLACK_SKIP_SIGNATURE_VERIFY=true`** — **do not** ship that to production.

Your Slack user id has to exist on the **`users.slack_user_id`** column or mapping will fail. Planner calls still want **`OPENAI_API_KEY`**.

If you want the bot to actually post in the thread, set **`SLACK_BOT_TOKEN`** (`xoxb-...`, `chat:write`). Without it you still get JSON back from the API, just silence in the channel.

**`SLACK_EVENTS_ASYNC`** defaults to `true` so Slack gets a fast `ok` while work continues in the background. Flip it to `false` when you want the full JSON in one HTTP response for debugging.

URL verification example (PowerShell — remember `curl` is often `Invoke-WebRequest`; `curl.exe` is the real one):

```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8000/slack/events" -Method POST -ContentType "application/json" -Body '{"type":"url_verification","challenge":"hello"}'
```

```powershell
curl.exe -s -X POST http://127.0.0.1:8000/slack/events -H "Content-Type: application/json" -d "{\"type\":\"url_verification\",\"challenge\":\"hello\"}"
```

Linux / Git Bash / WSL:

```bash
curl -s -X POST http://127.0.0.1:8000/slack/events -H "Content-Type: application/json" -d '{"type":"url_verification","challenge":"hello"}'
```

If you set **`REDIS_URL`**, the app boots a Redis client (used for things like `/chat` request counting when present).

---

## What’s actually here (short map)

**Orchestration (natural language → tool → DB):**

- `POST /chat` and `POST /chat/stream` — planner, validation, policy, execution, audit row
- `POST /clarify` — send a follow-up when the model asked for clarification
- `GET /audit/{id}` — pull one audit record

**Tasks (normal REST, no LLM in the middle):**

- `POST /tasks`, `GET /tasks`, `GET /tasks/{id}`, `PUT /tasks/{id}`, `DELETE /tasks/{id}`

**Summaries and insights:**

- `/summary/*` — daily summary, weekly retro
- `/insights/*` — productivity, priority, anomalies, explain endpoints, next-best-actions + feedback, and a combined **`GET /insights/snapshot`** if you want one round trip
- `/analytics/playback` — day-by-day KPI slices

**Other:**

- `/auth/*` — register, login, `me`
- `/ai/*` — parse text into tasks, roadmap planning, agent-style commands (OpenAI when configured)
- `/demo/*` — gated demo reset/scenarios/personas when `DEMO_MODE=true` and you are on the demo email
- `/slack/events` and `/slack/traces/{trace_id}` — Slack path + trace fetch

---

## Demo login

Handy if you turned on demo mode:

- **Email:** `demo@smarttracker.local`
- **Password:** `demo1234`

Demo-only routes will not cooperate unless **`DEMO_MODE=true`** and you are that user.
