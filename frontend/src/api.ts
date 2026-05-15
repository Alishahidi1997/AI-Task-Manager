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

export type PlaybackSnapshot = {
  at: string;
  completion: number;
  overdue_count: number;
  cycle_time_hours: number | null;
};

export type PlaybackResponse = {
  from: string;
  to: string;
  step: "day";
  snapshots: PlaybackSnapshot[];
};

export type AnomalyItem = {
  id: string;
  date: string;
  metric: "completion" | "overdue_count" | "cycle_time_hours";
  direction: "spike" | "drop";
  value: number;
  baseline_mean: number;
  z_score: number;
  confidence: number;
  likely_cause: string;
  impact: number;
};

export type AnomaliesResponse = {
  generated_at: string;
  window_days: number;
  baseline_days: number;
  snapshots_used: number;
  anomalies: AnomalyItem[];
};

export type InsightsSnapshotResponse = {
  generated_at: string;
  params: { anomaly_window_days: number; anomaly_baseline_days: number };
  productivity: { bucket_count: number; narrative: string };
  priority: {
    total_overdue: number;
    high_priority_overdue_in_view: number;
    tasks_previewed: number;
    suggestion: string;
  };
  anomalies: {
    window_days: number;
    baseline_days: number;
    flagged_count: number;
    snapshots_used: number;
    top: {
      metric: string;
      direction: string;
      impact: number;
      date: string;
      confidence?: number;
    } | null;
  };
  next_actions: {
    total_candidates: number;
    top_ranked: Array<{
      feedback_key: string;
      action_type: string;
      rank_score: number;
      task_title?: string;
    }>;
    suggestion: string;
  };
};

export type NextActionOutcome = "accepted" | "dismissed" | "completed";

export type NextActionItem = {
  id: string;
  task_id: number;
  task_title: string;
  category: string;
  hours_overdue: number;
  action_type: string;
  action: string;
  rank_score: number;
  feedback_key: string;
  learned_multiplier: number;
};

export type NextActionsResponse = {
  generated_at: string;
  suggestion: string;
  total_candidates: number;
  actions: NextActionItem[];
};

export type PersonaRole = "manager" | "analyst" | "executive";

export type PersonaCard = {
  id: string;
  title: string;
  variant: "metric_row" | "text" | "bullets" | "key_value" | "table";
  metrics?: { label: string; value: number }[];
  body?: string;
  footnote?: string;
  /** Bullet strings, or key/value rows depending on `variant`. */
  items?: string[] | { key: string; value: number }[];
  columns?: string[];
  rows?: Record<string, unknown>[];
};

export type PersonaDashboardResponse = {
  persona: PersonaRole;
  generated_at: string;
  lens: string;
  tagline: string;
  shared: {
    task_total: number;
    by_status: { todo: number; in_progress: number; done: number };
    overdue_open_total: number;
  };
  cards: PersonaCard[];
  action_queue?: Array<{
    task_id: number;
    title: string;
    priority: string;
    hours_overdue: number;
  }>;
  datasets?: {
    status_breakdown?: Record<string, number>;
    category_open_counts?: Record<string, number>;
    productivity_buckets?: unknown[];
  };
  headline?: string;
  weekly_metrics?: Record<string, unknown>;
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

export async function getInsightAnomalies(params?: {
  days?: number;
  baseline_days?: number;
}): Promise<AnomaliesResponse> {
  const query = new URLSearchParams();
  if (params?.days != null) query.set("days", String(params.days));
  if (params?.baseline_days != null) query.set("baseline_days", String(params.baseline_days));
  const q = query.toString();
  return request<AnomaliesResponse>(`/insights/anomalies${q ? `?${q}` : ""}`);
}

export async function getInsightsSnapshot(params?: {
  days?: number;
  baseline_days?: number;
}): Promise<InsightsSnapshotResponse> {
  const query = new URLSearchParams();
  if (params?.days != null) query.set("days", String(params.days));
  if (params?.baseline_days != null) query.set("baseline_days", String(params.baseline_days));
  const q = query.toString();
  return request<InsightsSnapshotResponse>(`/insights/snapshot${q ? `?${q}` : ""}`);
}

export async function getNextActions(): Promise<NextActionsResponse> {
  return request<NextActionsResponse>("/insights/next-actions");
}

export async function recordNextActionOutcome(
  feedbackKey: string,
  outcome: NextActionOutcome,
): Promise<{ ok: boolean; feedback_id: number; feedback_key: string; outcome: NextActionOutcome }> {
  return request<{ ok: boolean; feedback_id: number; feedback_key: string; outcome: NextActionOutcome }>(
    "/insights/next-actions/outcome",
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ feedback_key: feedbackKey, outcome }),
    },
  );
}

export async function applyNextAction(
  feedbackKey: string,
): Promise<{
  ok: boolean;
  action_type: string;
  feedback_key: string;
  task: { id: number; title: string; status: TaskStatus; due_date: string | null };
}> {
  return request<{
    ok: boolean;
    action_type: string;
    feedback_key: string;
    task: { id: number; title: string; status: TaskStatus; due_date: string | null };
  }>("/insights/next-actions/apply", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ feedback_key: feedbackKey }),
  });
}

export type ActionOutcomeBreakdown = {
  total: number;
  accepted: number;
  dismissed: number;
  completed: number;
  positive_rate: number;
};

export type ActionOutcomesResponse = {
  generated_at: string;
  window_days: number;
  totals: {
    all: number;
    accepted: number;
    dismissed: number;
    completed: number;
    overall_positive_rate: number;
  };
  by_action_type: Record<string, ActionOutcomeBreakdown>;
  summary: string;
  recent: Array<{
    id: number;
    action_type: string;
    outcome: string;
    feedback_key: string;
    created_at: string | null;
  }>;
};

export async function getNextActionOutcomes(days?: number): Promise<ActionOutcomesResponse> {
  const query = new URLSearchParams();
  if (days != null) query.set("days", String(days));
  const q = query.toString();
  return request<ActionOutcomesResponse>(`/insights/next-actions/outcomes${q ? `?${q}` : ""}`);
}

export async function getInsightExplanation(
  insightId: string,
  params?: { days?: number; baseline_days?: number },
): Promise<InsightExplanationResponse> {
  const query = new URLSearchParams();
  if (params?.days != null) query.set("days", String(params.days));
  if (params?.baseline_days != null) query.set("baseline_days", String(params.baseline_days));
  const q = query.toString();
  return request<InsightExplanationResponse>(
    `/insights/explain/${encodeURIComponent(insightId)}${q ? `?${q}` : ""}`,
  );
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

export async function getPersonaDashboard(role: PersonaRole): Promise<PersonaDashboardResponse> {
  return request<PersonaDashboardResponse>(
    `/demo/personas/${encodeURIComponent(role)}/dashboard`,
  );
}

export async function getAnalyticsPlayback(params: {
  from: string;
  to: string;
  step?: "day";
}): Promise<PlaybackResponse> {
  const query = new URLSearchParams();
  query.set("from", params.from);
  query.set("to", params.to);
  query.set("step", params.step ?? "day");
  return request<PlaybackResponse>(`/analytics/playback?${query.toString()}`);
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
