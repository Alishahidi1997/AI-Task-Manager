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

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, init);
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

export async function getWeeklyRetro(): Promise<WeeklyRetroResponse> {
  return request<WeeklyRetroResponse>("/summary/weekly-retro");
}
