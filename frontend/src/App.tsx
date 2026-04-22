import { useEffect, useMemo, useState } from "react";
import type { FormEvent } from "react";
import "./App.css";
import {
  createTask,
  deleteTask,
  getDailySummary,
  getWeeklyRetro,
  getPrioritySuggestions,
  getProductivityInsights,
  listTasks,
  updateTaskStatus,
} from "./api";
import type {
  DailySummaryResponse,
  PriorityResponse,
  ProductivityResponse,
  Task,
  TaskStatus,
  WeeklyRetroResponse,
} from "./api";

function App() {
  const [tasks, setTasks] = useState<Task[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string>("");
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [dueDate, setDueDate] = useState("");
  const [creating, setCreating] = useState(false);
  const [updatingTaskId, setUpdatingTaskId] = useState<number | null>(null);
  const [deletingTaskId, setDeletingTaskId] = useState<number | null>(null);
  const [filterStatus, setFilterStatus] = useState<"" | TaskStatus>("");
  const [filterDueBefore, setFilterDueBefore] = useState("");
  const [filterDueAfter, setFilterDueAfter] = useState("");
  const [dailySummary, setDailySummary] = useState<DailySummaryResponse | null>(null);
  const [weeklyRetro, setWeeklyRetro] = useState<WeeklyRetroResponse | null>(null);
  const [productivity, setProductivity] = useState<ProductivityResponse | null>(null);
  const [priority, setPriority] = useState<PriorityResponse | null>(null);
  const [insightsLoading, setInsightsLoading] = useState(false);
  const [insightsError, setInsightsError] = useState("");

  const statusCount = useMemo(() => {
    return tasks.reduce(
      (acc, task) => {
        acc[task.status] += 1;
        return acc;
      },
      { todo: 0, in_progress: 0, done: 0 },
    );
  }, [tasks]);

  async function loadTasks() {
    setLoading(true);
    setError("");
    try {
      const data = await listTasks({
        status: filterStatus,
        dueBefore: filterDueBefore,
        dueAfter: filterDueAfter,
      });
      setTasks(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong");
    } finally {
      setLoading(false);
    }
  }

  async function handleStatusChange(taskId: number, nextStatus: TaskStatus) {
    setUpdatingTaskId(taskId);
    setError("");
    try {
      await updateTaskStatus(taskId, nextStatus);
      await loadTasks();
      await loadInsights();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not update task");
    } finally {
      setUpdatingTaskId(null);
    }
  }

  async function handleDeleteTask(taskId: number) {
    setDeletingTaskId(taskId);
    setError("");
    try {
      await deleteTask(taskId);
      await loadTasks();
      await loadInsights();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not delete task");
    } finally {
      setDeletingTaskId(null);
    }
  }

  async function handleCreateTask(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (!title.trim()) {
      return;
    }

    setCreating(true);
    setError("");
    try {
      await createTask({
        title: title.trim(),
        description: description.trim() || null,
        due_date: dueDate ? new Date(dueDate).toISOString() : null,
      });
      setTitle("");
      setDescription("");
      setDueDate("");
      await loadTasks();
      await loadInsights();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not create task");
    } finally {
      setCreating(false);
    }
  }

  async function loadInsights() {
    setInsightsLoading(true);
    setInsightsError("");
    try {
      const [summaryData, weeklyRetroData, productivityData, priorityData] = await Promise.all([
        getDailySummary(),
        getWeeklyRetro(),
        getProductivityInsights(),
        getPrioritySuggestions(),
      ]);
      setDailySummary(summaryData);
      setWeeklyRetro(weeklyRetroData);
      setProductivity(productivityData);
      setPriority(priorityData);
    } catch (err) {
      setInsightsError(err instanceof Error ? err.message : "Could not load insights");
    } finally {
      setInsightsLoading(false);
    }
  }

  useEffect(() => {
    void loadTasks();
  }, [filterStatus, filterDueBefore, filterDueAfter]);

  useEffect(() => {
    void loadInsights();
  }, []);

  return (
    <main className="app-shell">
      <header className="topbar">
        <h1>Smart Task Tracker</h1>
        <p>FastAPI + React task dashboard</p>
      </header>

      <section className="panel stats">
        <div><strong>{tasks.length}</strong> total</div>
        <div><strong>{statusCount.todo}</strong> todo</div>
        <div><strong>{statusCount.in_progress}</strong> in progress</div>
        <div><strong>{statusCount.done}</strong> done</div>
      </section>

      <section className="panel">
        <h2>Filters</h2>
        <div className="filters">
          <label>
            Status
            <select
              value={filterStatus}
              onChange={(e) => setFilterStatus(e.target.value as "" | TaskStatus)}
            >
              <option value="">All</option>
              <option value="todo">todo</option>
              <option value="in_progress">in_progress</option>
              <option value="done">done</option>
            </select>
          </label>
          <label>
            Due before
            <input
              type="datetime-local"
              value={filterDueBefore}
              onChange={(e) => setFilterDueBefore(e.target.value)}
            />
          </label>
          <label>
            Due after
            <input
              type="datetime-local"
              value={filterDueAfter}
              onChange={(e) => setFilterDueAfter(e.target.value)}
            />
          </label>
          <button
            type="button"
            onClick={() => {
              setFilterStatus("");
              setFilterDueBefore("");
              setFilterDueAfter("");
            }}
          >
            Clear filters
          </button>
        </div>
      </section>

      <section className="panel">
        <h2>Create task</h2>
        <form onSubmit={handleCreateTask} className="task-form">
          <label>
            Title
            <input
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="Finish API docs"
              required
            />
          </label>
          <label>
            Description
            <textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Optional details"
            />
          </label>
          <label>
            Due date
            <input
              type="datetime-local"
              value={dueDate}
              onChange={(e) => setDueDate(e.target.value)}
            />
          </label>
          <button type="submit" disabled={creating}>
            {creating ? "Creating..." : "Add task"}
          </button>
        </form>
      </section>

      <section className="panel">
        <div className="list-head">
          <h2>Tasks</h2>
          <button type="button" onClick={() => void loadTasks()} disabled={loading}>
            {loading ? "Refreshing..." : "Refresh"}
          </button>
        </div>
        {error ? <p className="error">{error}</p> : null}
        {loading ? <p className="muted">Loading tasks...</p> : null}
        {!loading && tasks.length === 0 ? <p className="muted">No tasks match your filters yet.</p> : null}
        <ul className="task-list">
          {tasks.map((task) => (
            <li key={task.id}>
              <div className="row">
                <strong>{task.title}</strong>
                <span className={`badge ${task.status}`}>{task.status}</span>
              </div>
              {task.description ? <p>{task.description}</p> : null}
              <small>
                category: {task.category ?? "n/a"} | due: {task.due_date ?? "n/a"}
              </small>
              <div className="task-actions">
                <select
                  value={task.status}
                  onChange={(e) => void handleStatusChange(task.id, e.target.value as TaskStatus)}
                  disabled={updatingTaskId === task.id}
                >
                  <option value="todo">todo</option>
                  <option value="in_progress">in_progress</option>
                  <option value="done">done</option>
                </select>
                <button
                  type="button"
                  className="danger"
                  onClick={() => void handleDeleteTask(task.id)}
                  disabled={deletingTaskId === task.id}
                >
                  {deletingTaskId === task.id ? "Deleting..." : "Delete"}
                </button>
              </div>
            </li>
          ))}
        </ul>
      </section>

      <section className="panel">
        <h2>Weekly retro</h2>
        {weeklyRetro ? (
          <div className="insight-block">
            <small>
              completed: {weeklyRetro.metrics.completed_this_week} | overdue:{" "}
              {weeklyRetro.metrics.overdue_open_tasks}
            </small>
            <p>
              <strong>What went well:</strong> {weeklyRetro.what_went_well}
            </p>
            <p>
              <strong>What slipped:</strong> {weeklyRetro.what_slipped}
            </p>
            <p>
              <strong>Next week focus:</strong> {weeklyRetro.next_week_focus}
            </p>
          </div>
        ) : (
          <p className="muted">No weekly retro data yet.</p>
        )}
      </section>

      <section className="panel">
        <div className="list-head">
          <h2>Daily summary</h2>
          <button type="button" onClick={() => void loadInsights()} disabled={insightsLoading}>
            {insightsLoading ? "Refreshing..." : "Refresh insights"}
          </button>
        </div>
        {insightsError ? <p className="error">{insightsError}</p> : null}
        {insightsLoading ? <p className="muted">Loading insights...</p> : null}
        {dailySummary ? (
          <div className="insight-block">
            <p>{dailySummary.summary}</p>
            <small>
              mode: {dailySummary.mode} | based on {dailySummary.task_count} completed tasks
            </small>
          </div>
        ) : (
          <p>No summary yet.</p>
        )}
      </section>

      <section className="panel">
        <h2>Productivity insights</h2>
        {productivity ? (
          <div className="insight-block">
            <p>{productivity.narrative}</p>
            <ul className="simple-list">
              {productivity.buckets.map((bucket) => (
                <li key={bucket.category}>
                  <strong>{bucket.category}</strong>: {bucket.tasks_completed} tasks, avg{" "}
                  {bucket.avg_hours_to_complete}h
                </li>
              ))}
            </ul>
          </div>
        ) : (
          <p className="muted">No productivity data yet.</p>
        )}
      </section>

      <section className="panel">
        <h2>Priority suggestions</h2>
        {priority ? (
          <div className="insight-block">
            <p>{priority.suggestion}</p>
            <small>total overdue: {priority.total_overdue}</small>
            <ul className="simple-list">
              {priority.tasks.slice(0, 8).map((item) => (
                <li key={item.id}>
                  <strong>{item.title}</strong> ({item.priority}) - {item.hours_overdue}h overdue
                </li>
              ))}
            </ul>
          </div>
        ) : (
          <p className="muted">No overdue tasks right now.</p>
        )}
      </section>
    </main>
  );
}

export default App;
