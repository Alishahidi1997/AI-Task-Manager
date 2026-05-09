# AI Middleware Workflow for Smart Task Tracker

This document explains the architecture where an LLM is used as a middleware/orchestration layer, not as the final authority. It is written so you can paste it into GPT and ask for summaries by layer, risk, or execution flow.

`project.md` is the source of truth. This file is a GPT-friendly explanation companion.

## 1) Core idea

Use the LLM to interpret user intent and select the right internal tool/action.

- The LLM decides: "Which tool should be called?" and "What fields should be filled?"
- The server decides: "Is this allowed?", "Are fields valid?", and "Should execution happen?"
- The database is updated only by trusted server logic, never directly by model output.

In short:

- LLM = planner/interpreter
- API/backend = policy + validator + executor

## 2) Why this pattern is strong

- Natural language UX without exposing unsafe execution.
- Centralized validation and authorization checks.
- Easy to add more tools without changing client UX.
- Optional fields are handled gracefully (if missing, default/null behavior applies).
- Clear audit trail of intent -> selected action -> executed result.
- Works with channel adapters like Slack/email/API clients without a frontend dependency.

## 3) Layered architecture

### Layer A: Client/Input Layer

- Accepts free-text user requests.
- Example: "Create a task for tomorrow 5pm, assign to Alex, mark high priority."

### Layer B: Auth + Identity Layer

- Verifies user identity (token/session).
- Adds tenant/user context (who is making the request).

### Layer C: AI Middleware Orchestrator

- Builds the LLM prompt with:
  - allowed tools
  - field schema for each tool
  - optional vs required fields
  - user/role constraints
  - timezone/date parsing hints
- Sends request to LLM for tool selection and structured arguments.

### Layer D: Structured Output Validation

- Parse LLM output as strict JSON.
- Reject if malformed JSON or non-allowed tool.
- Validate fields against schema.
- Drop or reject unknown fields.

### Layer E: Policy + Authorization Layer

- Confirms user can call selected tool.
- Confirms target entities are allowed (assignee, project, team, tenant).
- Applies business rules (status transitions, due-date constraints, etc.).

### Layer F: Execution Layer

- Calls internal service/endpoint with validated arguments.
- Example: create task, update status, assign owner.

### Layer G: Persistence + Audit Layer

- Writes changes using server-side DB logic.
- Stores audit metadata:
  - request text
  - chosen tool
  - arguments
  - validator result
  - execution outcome

### Layer H: Response Layer

- Returns a user-friendly response plus structured result.
- If required fields are missing/ambiguous, returns clarification prompts.

## 4) End-to-end workflow (step by step)

1. User sends natural language command.
2. Server authenticates user and loads user context.
3. Orchestrator prepares tool specs + schema + constraints.
4. LLM returns structured plan: `tool_name`, `arguments`, `confidence`.
5. Server validates tool + argument schema.
6. Server runs authorization/policy checks.
7. If valid, execute internal action.
8. Persist result and audit trail.
9. Return confirmation/result to client.
10. If invalid/ambiguous, return clarification instead of executing.

## 5) Example with optional fields

User says:

"Create task tomorrow at 5pm. Must be done."

LLM may return:

- tool: `create_task`
- args:
  - title: inferred from text
  - due_date: parsed as tomorrow 5pm in user timezone
  - status: `todo` (or `in_progress`, based on policy)
  - assignee: omitted (optional)

Server behavior:

- If `assignee` is optional and missing -> proceed with null/default.
- If `assignee` was provided but unauthorized -> reject or request correction.

## 6) Request/response contract recommendation

Use strict planner output format:

- `tool_name` (string, must be in allowlist)
- `arguments` (object, schema-validated)
- `confidence` (number 0..1)
- `missing_required` (array of fields if any)
- `clarification_question` (optional)

Execution should only occur when:

- tool is allowed
- schema is valid
- authz passes
- no missing required fields

## 7) Security and reliability checklist

- Tool allowlist per role/user.
- JSON schema validation before execution.
- Authorization check after parsing.
- Tenant isolation checks.
- Rate limiting for LLM + action execution.
- Idempotency keys for write operations.
- Audit logs for every planned/executed action.
- Human-readable error messages for rejected plans.

## 8) Failure paths

- LLM picks unknown tool -> reject and return safe error.
- LLM output not JSON -> retry or clarification flow.
- Missing required fields -> ask user follow-up question.
- AuthZ failed -> deny execution.
- Execution failed -> return controlled error + log incident.

## 9) Suggested diagram for presentations

Use this flow:

User Input (Slack/Email/API) -> Auth -> AI Planner -> Schema Validator -> Policy/AuthZ -> Executor -> DB/Audit -> Response

And add a side branch from Validator/AuthZ to:

Clarification/Reject -> Response

## 10) Summary sentence

This architecture treats the LLM as an intelligent routing/planning middleware, while the backend remains the source of truth for security, validation, and final execution.
