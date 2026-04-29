import { useEffect, useMemo, useState } from "react";
import type { FormEvent } from "react";
import "./App.css";
import {
  getMe,
  hasAuthToken,
  createTask,
  deleteTask,
  getDailySummary,
  getWeeklyRetro,
  getPrioritySuggestions,
  getProductivityInsights,
  getInsightExplanation,
  listDemoScenarios,
  login,
  loadDemoScenario,
  planTaskRoadmap,
  parseTaskText,
  listTasks,
  register,
  resetDemoData,
  setAuthToken,
  updateTaskStatus,
} from "./api";
import { AuthPanel } from "./components/AuthPanel";
import { TaskComposerPanel } from "./components/TaskComposerPanel";
import { TaskListPanel } from "./components/TaskListPanel";
import type {
  AuthUser,
  DailySummaryResponse,
  DemoScenario,
  InsightExplanationResponse,
  PlannedRoadmapTask,
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
  const [authMode, setAuthMode] = useState<"login" | "register">("login");
  const [authEmail, setAuthEmail] = useState("demo@smarttracker.local");
  const [authPassword, setAuthPassword] = useState("demo1234");
  const [authLoading, setAuthLoading] = useState(false);
  const [authError, setAuthError] = useState("");
  const [currentUser, setCurrentUser] = useState<AuthUser | null>(null);
  const [resettingDemo, setResettingDemo] = useState(false);
  const [demoScenarios, setDemoScenarios] = useState<DemoScenario[]>([]);
  const [selectedScenarioId, setSelectedScenarioId] = useState("default");
  const [loadingScenarios, setLoadingScenarios] = useState(false);
  const [loadingScenario, setLoadingScenario] = useState(false);
  const [aiInput, setAiInput] = useState("");
  const [aiLoading, setAiLoading] = useState(false);
  const [aiPlanLoading, setAiPlanLoading] = useState(false);
  const [aiCreateRoadmapLoading, setAiCreateRoadmapLoading] = useState(false);
  const [aiNote, setAiNote] = useState("");
  const [roadmapTitle, setRoadmapTitle] = useState("");
  const [roadmapMode, setRoadmapMode] = useState("");
  const [roadmapReason, setRoadmapReason] = useState("");
  const [roadmapTasks, setRoadmapTasks] = useState<PlannedRoadmapTask[]>([]);
  const [insightExplanations, setInsightExplanations] = useState<
    Record<string, InsightExplanationResponse | null>
  >({});
  const [explainingInsightId, setExplainingInsightId] = useState<string | null>(null);

  const statusCount = useMemo(() => {
    return tasks.reduce(
      (acc, task) => {
        acc[task.status] += 1;
        return acc;
      },
      { todo: 0, in_progress: 0, done: 0 },
    );
  }, [tasks]);

  const isAuthenticated = currentUser !== null;
  const isDemoUser = currentUser?.email === "demo@smarttracker.local";

  async function loadTasks() {
    if (!isAuthenticated) return;
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
    if (!isAuthenticated) return;
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
  }, [filterStatus, filterDueBefore, filterDueAfter, isAuthenticated]);

  useEffect(() => {
    void loadInsights();
  }, [isAuthenticated]);

  async function hydrateUserFromToken() {
    if (!hasAuthToken()) return
    try {
      const me = await getMe();
      setCurrentUser(me);
    } catch {
      setAuthToken("");
      setCurrentUser(null);
    }
  }

  useEffect(() => {
    void hydrateUserFromToken();
  }, []);

  useEffect(() => {
    if (isDemoUser) {
      void loadScenarios();
      return;
    }
    setDemoScenarios([]);
    setSelectedScenarioId("default");
  }, [isDemoUser]);

  async function handleAuthSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setAuthLoading(true);
    setAuthError("");
    try {
      const result =
        authMode === "login"
          ? await login(authEmail.trim(), authPassword)
          : await register(authEmail.trim(), authPassword);
      setAuthToken(result.access_token);
      setCurrentUser(result.user);
    } catch (err) {
      setAuthError(err instanceof Error ? err.message : "Authentication failed");
    } finally {
      setAuthLoading(false);
    }
  }

  function handleLogout() {
    setAuthToken("");
    setCurrentUser(null);
    setTasks([]);
    setDailySummary(null);
    setWeeklyRetro(null);
    setProductivity(null);
    setPriority(null);
  }

  async function handleResetDemo() {
    setResettingDemo(true);
    setError("");
    try {
      await resetDemoData();
      await loadTasks();
      await loadInsights();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not reset demo data");
    } finally {
      setResettingDemo(false);
    }
  }

  async function loadScenarios() {
    if (!isDemoUser) return;
    setLoadingScenarios(true);
    setError("");
    try {
      const response = await listDemoScenarios();
      setDemoScenarios(response.scenarios);
      if (!response.scenarios.some((item) => item.id === selectedScenarioId)) {
        setSelectedScenarioId(response.scenarios[0]?.id ?? "default");
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load demo scenarios");
    } finally {
      setLoadingScenarios(false);
    }
  }

  async function handleLoadScenario() {
    if (!selectedScenarioId) return;
    setLoadingScenario(true);
    setError("");
    try {
      await loadDemoScenario(selectedScenarioId);
      await loadTasks();
      await loadInsights();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load demo scenario");
    } finally {
      setLoadingScenario(false);
    }
  }

  async function handleAiParse() {
    if (!aiInput.trim()) return;
    setAiLoading(true);
    setAiNote("");
    setError("");
    try {
      const parsed = await parseTaskText(aiInput.trim());
      setTitle(parsed.title ?? "");
      setDescription(parsed.description ?? "");
      if (parsed.due_date) {
        const local = new Date(parsed.due_date);
        const pad = (n: number) => String(n).padStart(2, "0");
        const dtLocal = `${local.getFullYear()}-${pad(local.getMonth() + 1)}-${pad(local.getDate())}T${pad(local.getHours())}:${pad(local.getMinutes())}`;
        setDueDate(dtLocal);
      }
      const reasonText = parsed.reason ? ` ${parsed.reason}` : "";
      setAiNote(`Parsed with ${parsed.mode} (${parsed.confidence} confidence).${reasonText}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not parse AI task input");
    } finally {
      setAiLoading(false);
    }
  }

  async function handleAiPlan() {
    if (!aiInput.trim()) return;
    setAiPlanLoading(true);
    setAiNote("");
    setError("");
    try {
      const roadmap = await planTaskRoadmap(aiInput.trim(), 7);
      setRoadmapTitle(roadmap.roadmap_title);
      setRoadmapMode(roadmap.mode);
      setRoadmapReason(roadmap.reason ?? "");
      setRoadmapTasks(roadmap.tasks);
      setAiNote(`Roadmap generated with ${roadmap.mode} (${roadmap.tasks.length} task steps).`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not generate roadmap");
    } finally {
      setAiPlanLoading(false);
    }
  }

  async function handleCreateRoadmapTasks() {
    if (roadmapTasks.length === 0) return;
    setAiCreateRoadmapLoading(true);
    setError("");
    try {
      for (const task of roadmapTasks) {
        await createTask({
          title: task.title,
          description: task.description,
          due_date: task.due_date,
          category: task.category,
        });
      }
      await loadTasks();
      await loadInsights();
      setAiNote(`Created ${roadmapTasks.length} roadmap task(s).`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not create roadmap tasks");
    } finally {
      setAiCreateRoadmapLoading(false);
    }
  }

  async function handleExplainInsight(insightId: string) {
    setExplainingInsightId(insightId);
    setError("");
    try {
      const data = await getInsightExplanation(insightId);
      setInsightExplanations((prev) => ({ ...prev, [insightId]: data }));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load insight explanation");
    } finally {
      setExplainingInsightId(null);
    }
  }

  return (
    <main className="app-shell">
      <header className="topbar">
        <h1>Smart Task Tracker</h1>
        <p>
          FastAPI + React task dashboard
          {currentUser ? ` | ${currentUser.email}` : ""}
        </p>
      </header>

      {!isAuthenticated ? (
        <AuthPanel
          authMode={authMode}
          authEmail={authEmail}
          authPassword={authPassword}
          authLoading={authLoading}
          authError={authError}
          onSubmit={handleAuthSubmit}
          onToggleMode={() => setAuthMode(authMode === "login" ? "register" : "login")}
          onEmailChange={setAuthEmail}
          onPasswordChange={setAuthPassword}
        />
      ) : null}

      {isAuthenticated ? (
        <>
          <section className="panel">
            <div className="list-head">
              <h2>Session</h2>
              <div className="task-actions">
                {isDemoUser ? (
                  <button
                    type="button"
                    onClick={() => void handleResetDemo()}
                    disabled={resettingDemo || loadingScenario}
                  >
                    {resettingDemo ? "Resetting demo..." : "Reset demo data"}
                  </button>
                ) : null}
                <button type="button" className="danger" onClick={handleLogout}>
                  Logout
                </button>
              </div>
            </div>
            <p className="muted">Your data is isolated to this account.</p>
            {isDemoUser ? (
              <>
                <p className="muted">
                  Demo mode reset/scenario loading requires backend env: <code>DEMO_MODE=true</code>.
                </p>
                <div className="task-actions">
                  <select
                    value={selectedScenarioId}
                    onChange={(e) => setSelectedScenarioId(e.target.value)}
                    disabled={loadingScenarios || loadingScenario || resettingDemo}
                  >
                    {demoScenarios.map((scenario) => (
                      <option key={scenario.id} value={scenario.id}>
                        {scenario.label}
                      </option>
                    ))}
                  </select>
                  <button
                    type="button"
                    onClick={() => void handleLoadScenario()}
                    disabled={
                      loadingScenarios ||
                      loadingScenario ||
                      resettingDemo ||
                      demoScenarios.length === 0
                    }
                  >
                    {loadingScenario ? "Loading scenario..." : "Load scenario"}
                  </button>
                  <button
                    type="button"
                    onClick={() => void loadScenarios()}
                    disabled={loadingScenarios || loadingScenario || resettingDemo}
                  >
                    {loadingScenarios ? "Refreshing..." : "Refresh scenarios"}
                  </button>
                </div>
                {demoScenarios.length > 0 ? (
                  <p className="muted">
                    {demoScenarios.find((scenario) => scenario.id === selectedScenarioId)?.description}
                  </p>
                ) : null}
              </>
            ) : null}
          </section>

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

          <TaskComposerPanel
            aiInput={aiInput}
            aiLoading={aiLoading}
            aiPlanLoading={aiPlanLoading}
            aiCreateRoadmapLoading={aiCreateRoadmapLoading}
            aiNote={aiNote}
            roadmapTitle={roadmapTitle}
            roadmapMode={roadmapMode}
            roadmapReason={roadmapReason}
            roadmapTasks={roadmapTasks}
            title={title}
            description={description}
            dueDate={dueDate}
            creating={creating}
            onAiInputChange={setAiInput}
            onAiParse={handleAiParse}
            onAiPlan={handleAiPlan}
            onCreateRoadmapTasks={handleCreateRoadmapTasks}
            onSubmit={handleCreateTask}
            onTitleChange={setTitle}
            onDescriptionChange={setDescription}
            onDueDateChange={setDueDate}
          />

          <TaskListPanel
            tasks={tasks}
            loading={loading}
            error={error}
            updatingTaskId={updatingTaskId}
            deletingTaskId={deletingTaskId}
            onRefresh={loadTasks}
            onStatusChange={handleStatusChange}
            onDeleteTask={handleDeleteTask}
          />

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
        <div className="list-head">
          <h2>Productivity insights</h2>
          <button
            type="button"
            onClick={() => void handleExplainInsight("productivity")}
            disabled={explainingInsightId === "productivity"}
          >
            {explainingInsightId === "productivity" ? "Loading why..." : "Why this insight?"}
          </button>
        </div>
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
            {insightExplanations.productivity ? (
              <div className="insight-why">
                <small>
                  <strong>{insightExplanations.productivity.title}</strong>
                </small>
                <ul className="simple-list">
                  {insightExplanations.productivity.why.map((item) => (
                    <li key={item}>{item}</li>
                  ))}
                </ul>
              </div>
            ) : null}
          </div>
        ) : (
          <p className="muted">No productivity data yet.</p>
        )}
      </section>

      <section className="panel">
        <div className="list-head">
          <h2>Priority suggestions</h2>
          <button
            type="button"
            onClick={() => void handleExplainInsight("priority")}
            disabled={explainingInsightId === "priority"}
          >
            {explainingInsightId === "priority" ? "Loading why..." : "Why this insight?"}
          </button>
        </div>
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
            {insightExplanations.priority ? (
              <div className="insight-why">
                <small>
                  <strong>{insightExplanations.priority.title}</strong>
                </small>
                <ul className="simple-list">
                  {insightExplanations.priority.why.map((item) => (
                    <li key={item}>{item}</li>
                  ))}
                </ul>
              </div>
            ) : null}
          </div>
        ) : (
          <p className="muted">No overdue tasks right now.</p>
        )}
          </section>
        </>
      ) : null}
    </main>
  );
}

export default App;
