export type TaskStatus = "todo" | "in_progress" | "done";
export type TaskCategory = "today" | "this_week" | "routine" | "backlog";

export type Task = {
  id: number;
  title: string;
  description: string | null;
  status: TaskStatus;
  due_date: string | null;
  category: TaskCategory | null;
};

export type DailySummaryResponse = {
  summary: string;
  task_count: number;
  mode: string;
};

export type ProductivityBucket = {
  category: string;
  tasks_completed: number;
  avg_hours_to_complete: number;
};

export type ProductivityResponse = {
  buckets: ProductivityBucket[];
  narrative: string;
};

export type PriorityTask = {
  id: number;
  title: string;
  status: TaskStatus;
  due_date: string;
  category: string;
  hours_overdue: number;
  priority: "low" | "medium" | "high";
};

export type PriorityResponse = {
  generated_at: string;
  total_overdue: number;
  suggestion: string;
  tasks: PriorityTask[];
};

export type WeeklyRetroResponse = {
  generated_at: string;
  window_days: number;
  metrics: {
    completed_this_week: number;
    overdue_open_tasks: number;
    top_completed_bucket: string | null;
    top_slipping_bucket: string | null;
  };
  what_went_well: string;
  what_slipped: string;
  next_week_focus: string;
};

export type InsightExplanationResponse = {
  insight_id: string;
  title: string;
  why: string[];
  generated_at: string;
};

export type AuthUser = {
  id: number;
  email: string;
};

export type AuthResponse = {
  access_token: string;
  token_type: "bearer";
  user: AuthUser;
};

export type ParsedTaskResponse = {
  title: string;
  description: string | null;
  due_date: string | null;
  category: TaskCategory;
  confidence: "low" | "medium" | "high";
  mode: "openai" | "fallback";
  reason?: string;
};

export type PlannedRoadmapTask = {
  order: number;
  title: string;
  description: string | null;
  due_date: string | null;
  category: TaskCategory;
  priority: "low" | "medium" | "high";
};

export type PlannedRoadmapResponse = {
  roadmap_title: string;
  tasks: PlannedRoadmapTask[];
  mode: "openai" | "fallback";
  reason?: string;
};

export type AgentActionResult = {
  tool: string;
  ok: boolean;
  detail?: string;
  task_id?: number;
  dry_run?: boolean;
  task_preview?: {
    title: string;
    description: string | null;
    due_date: string | null;
    category: TaskCategory;
  };
};

export type AgentCommandResponse = {
  ok: boolean;
  mode: string;
  assistant_message: string;
  actions: AgentActionResult[];
  tool_calls_count?: number;
  dry_run?: boolean;
};

export type DemoScenario = {
  id: string;
  label: string;
  description: string;
};

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000";
const TOKEN_KEY = "smart_tracker_token";

let authToken = localStorage.getItem(TOKEN_KEY) ?? "";

export function setAuthToken(token: string) {
  authToken = token;
  if (token) {
    localStorage.setItem(TOKEN_KEY, token);
  } else {
    localStorage.removeItem(TOKEN_KEY);
  }
}

export function hasAuthToken() {
  return Boolean(authToken);
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers ?? {});
  if (authToken) {
    headers.set("Authorization", `Bearer ${authToken}`);
  }
  const response = await fetch(`${API_BASE_URL}${path}`, { ...init, headers });
  if (!response.ok) {
    throw new Error(`${init?.method ?? "GET"} ${path} failed (${response.status})`);
  }
  if (response.status === 204) {
    return undefined as T;
  }
  return (await response.json()) as T;
}

export async function listTasks(filters: {
  status?: "" | TaskStatus;
  dueBefore?: string;
  dueAfter?: string;
}): Promise<Task[]> {
  const params = new URLSearchParams();
  if (filters.status) params.set("status", filters.status);
  if (filters.dueBefore) params.set("due_before", new Date(filters.dueBefore).toISOString());
  if (filters.dueAfter) params.set("due_after", new Date(filters.dueAfter).toISOString());
  const q = params.toString();
  return request<Task[]>(`/tasks${q ? `?${q}` : ""}`);
}

export async function createTask(payload: {
  title: string;
  description: string | null;
  due_date: string | null;
  category?: TaskCategory | null;
}): Promise<Task> {
  return request<Task>("/tasks", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export async function updateTaskStatus(taskId: number, status: TaskStatus): Promise<Task> {
  return request<Task>(`/tasks/${taskId}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ status }),
  });
}

export async function deleteTask(taskId: number): Promise<void> {
  return request<void>(`/tasks/${taskId}`, { method: "DELETE" });
}

export async function getDailySummary(): Promise<DailySummaryResponse> {
  return request<DailySummaryResponse>("/summary/daily");
}

export async function getProductivityInsights(): Promise<ProductivityResponse> {
  return request<ProductivityResponse>("/insights/productivity");
}

export async function getPrioritySuggestions(): Promise<PriorityResponse> {
  return request<PriorityResponse>("/insights/priority");
}

export async function getInsightExplanation(
  insightId: string,
): Promise<InsightExplanationResponse> {
  return request<InsightExplanationResponse>(`/insights/explain/${encodeURIComponent(insightId)}`);
}

export async function getWeeklyRetro(): Promise<WeeklyRetroResponse> {
  return request<WeeklyRetroResponse>("/summary/weekly-retro");
}

export async function register(email: string, password: string): Promise<AuthResponse> {
  return request<AuthResponse>("/auth/register", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
}

export async function login(email: string, password: string): Promise<AuthResponse> {
  return request<AuthResponse>("/auth/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
}

export async function getMe(): Promise<AuthUser> {
  return request<AuthUser>("/auth/me");
}

export async function resetDemoData(): Promise<{ ok: boolean; seeded_tasks: number }> {
  return request<{ ok: boolean; seeded_tasks: number }>("/demo/reset", {
    method: "POST",
  });
}

export async function listDemoScenarios(): Promise<{ ok: boolean; scenarios: DemoScenario[] }> {
  return request<{ ok: boolean; scenarios: DemoScenario[] }>("/demo/scenarios");
}

export async function loadDemoScenario(
  scenarioId: string,
): Promise<{ ok: boolean; scenario_id: string; seeded_tasks: number }> {
  return request<{ ok: boolean; scenario_id: string; seeded_tasks: number }>(
    `/demo/load/${encodeURIComponent(scenarioId)}`,
    {
      method: "POST",
    },
  );
}

export async function parseTaskText(text: string): Promise<ParsedTaskResponse> {
  const userTimezone = Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC";
  return request<ParsedTaskResponse>("/ai/parse-task", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text, timezone: userTimezone }),
  });
}

export async function planTaskRoadmap(
  text: string,
  horizonDays = 7,
): Promise<PlannedRoadmapResponse> {
  const userTimezone = Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC";
  return request<PlannedRoadmapResponse>("/ai/plan-task", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text, timezone: userTimezone, horizon_days: horizonDays }),
  });
}

export async function runAgentCommand(
  query: string,
  dryRun = true,
): Promise<AgentCommandResponse> {
  const userTimezone = Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC";
  return request<AgentCommandResponse>("/ai/agent-command", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ query, timezone: userTimezone, dry_run: dryRun }),
  });
}
