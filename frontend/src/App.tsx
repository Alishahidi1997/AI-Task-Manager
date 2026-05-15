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
  getInsightAnomalies,
  getInsightsSnapshot,
  getNextActions,
  recordNextActionOutcome,
  applyNextAction,
  getNextActionOutcomes,
  getAnalyticsPlayback,
  listDemoScenarios,
  login,
  loadDemoScenario,
  getPersonaDashboard,
  planTaskRoadmap,
  parseTaskText,
  runAgentCommand,
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
  AgentActionResult,
  PlannedRoadmapTask,
  PriorityResponse,
  ProductivityResponse,
  Task,
  TaskStatus,
  PlaybackResponse,
  AnomaliesResponse,
  InsightsSnapshotResponse,
  NextActionsResponse,
  NextActionOutcome,
  ActionOutcomesResponse,
  PersonaCard,
  PersonaDashboardResponse,
  PersonaRole,
  WeeklyRetroResponse,
} from "./api";

function PersonaCardBlock({ card }: { card: PersonaCard }) {
  if (card.variant === "metric_row") {
    return (
      <div className="persona-metrics">
        {card.metrics?.map((m) => (
          <span key={m.label}>
            <strong>{m.value}</strong> {m.label}
          </span>
        ))}
      </div>
    );
  }
  if (card.variant === "text") {
    return (
      <>
        <p>{card.body}</p>
        {card.footnote ? <small className="muted">{card.footnote}</small> : null}
      </>
    );
  }
  if (card.variant === "bullets") {
    const lines = card.items?.filter((x): x is string => typeof x === "string") ?? [];
    return (
      <ul className="simple-list">
        {lines.map((item) => (
          <li key={item}>{item}</li>
        ))}
      </ul>
    );
  }
  if (card.variant === "key_value") {
    const rows =
      card.items?.filter(
        (x): x is { key: string; value: number } =>
          typeof x === "object" && x !== null && "key" in x,
      ) ?? [];
    return (
      <ul className="simple-list">
        {rows.map((row) => (
          <li key={row.key}>
            <strong>{row.key}</strong>: {row.value}
          </li>
        ))}
      </ul>
    );
  }
  if (card.variant === "table" && card.rows?.length) {
    const cols = card.columns?.length ? card.columns : Object.keys(card.rows[0] ?? {});
    return (
      <table className="persona-table">
        <thead>
          <tr>
            {cols.map((c) => (
              <th key={c}>{c}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {card.rows.map((row, i) => (
            <tr key={i}>
              {cols.map((c) => (
                <td key={c}>{String((row as Record<string, unknown>)[c] ?? "")}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    );
  }
  return null;
}

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
  const [agentQuery, setAgentQuery] = useState("");
  const [agentLoading, setAgentLoading] = useState(false);
  const [agentExecuting, setAgentExecuting] = useState(false);
  const [agentActions, setAgentActions] = useState<AgentActionResult[]>([]);
  const [agentMessage, setAgentMessage] = useState("");
  const [playback, setPlayback] = useState<PlaybackResponse | null>(null);
  const [playbackLoading, setPlaybackLoading] = useState(false);
  const [playbackError, setPlaybackError] = useState("");
  const [playbackPresetDays, setPlaybackPresetDays] = useState<30 | 60 | 90>(30);
  const [playbackCursor, setPlaybackCursor] = useState(0);
  const [anomalies, setAnomalies] = useState<AnomaliesResponse | null>(null);
  const [insightsSnapshot, setInsightsSnapshot] = useState<InsightsSnapshotResponse | null>(null);
  const [snapshotLoading, setSnapshotLoading] = useState(false);
  const [nextActions, setNextActions] = useState<NextActionsResponse | null>(null);
  const [actionOutcomes, setActionOutcomes] = useState<ActionOutcomesResponse | null>(null);
  const [updatingNextActionKey, setUpdatingNextActionKey] = useState<string | null>(null);
  const [applyingNextActionKey, setApplyingNextActionKey] = useState<string | null>(null);
  const [personaRole, setPersonaRole] = useState<PersonaRole>("manager");
  const [personaDash, setPersonaDash] = useState<PersonaDashboardResponse | null>(null);
  const [personaLoading, setPersonaLoading] = useState(false);
  const [personaError, setPersonaError] = useState("");

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
      await loadPlayback(playbackPresetDays);
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
      await loadPlayback(playbackPresetDays);
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
      await loadPlayback(playbackPresetDays);
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
      const [
        summaryData,
        weeklyRetroData,
        productivityData,
        priorityData,
        anomaliesData,
        nextActionsData,
        outcomesData,
      ] = await Promise.all([
        getDailySummary(),
        getWeeklyRetro(),
        getProductivityInsights(),
        getPrioritySuggestions(),
        getInsightAnomalies(),
        getNextActions(),
        getNextActionOutcomes(90),
      ]);
      setDailySummary(summaryData);
      setWeeklyRetro(weeklyRetroData);
      setProductivity(productivityData);
      setPriority(priorityData);
      setAnomalies(anomaliesData);
      setNextActions(nextActionsData);
      setActionOutcomes(outcomesData);
    } catch (err) {
      setInsightsError(err instanceof Error ? err.message : "Could not load insights");
    } finally {
      setInsightsLoading(false);
    }
  }

  async function loadInsightsSnapshot() {
    if (!isAuthenticated) return;
    setSnapshotLoading(true);
    setError("");
    try {
      const data = await getInsightsSnapshot({
        days: anomalies?.window_days ?? 30,
        baseline_days: anomalies?.baseline_days ?? 7,
      });
      setInsightsSnapshot(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load insights snapshot");
    } finally {
      setSnapshotLoading(false);
    }
  }

  function rangeForPreset(days: 30 | 60 | 90): { from: string; to: string } {
    const now = new Date();
    const to = now.toISOString();
    const fromDate = new Date(now);
    fromDate.setUTCDate(fromDate.getUTCDate() - (days - 1));
    const from = fromDate.toISOString();
    return { from, to };
  }

  async function loadPlayback(presetDays: 30 | 60 | 90 = playbackPresetDays) {
    if (!isAuthenticated) return;
    setPlaybackLoading(true);
    setPlaybackError("");
    try {
      const range = rangeForPreset(presetDays);
      const data = await getAnalyticsPlayback({
        from: range.from,
        to: range.to,
        step: "day",
      });
      setPlayback(data);
      setPlaybackCursor(Math.max(0, data.snapshots.length - 1));
    } catch (err) {
      setPlaybackError(err instanceof Error ? err.message : "Could not load KPI playback");
    } finally {
      setPlaybackLoading(false);
    }
  }

  useEffect(() => {
    void loadTasks();
  }, [filterStatus, filterDueBefore, filterDueAfter, isAuthenticated]);

  useEffect(() => {
    void loadInsights();
  }, [isAuthenticated]);

  useEffect(() => {
    if (!isAuthenticated) return;
    void loadPlayback(playbackPresetDays);
  }, [isAuthenticated, playbackPresetDays]);

  async function loadPersonaDashboard(role: PersonaRole = personaRole) {
    if (!isAuthenticated || !isDemoUser) return;
    setPersonaLoading(true);
    setPersonaError("");
    try {
      const data = await getPersonaDashboard(role);
      setPersonaDash(data);
    } catch (err) {
      setPersonaDash(null);
      setPersonaError(err instanceof Error ? err.message : "Could not load persona dashboard");
    } finally {
      setPersonaLoading(false);
    }
  }

  useEffect(() => {
    if (!isDemoUser) {
      setPersonaDash(null);
      setPersonaError("");
      return;
    }
    void loadPersonaDashboard(personaRole);
  }, [isDemoUser, personaRole]);

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
    setPlayback(null);
    setAnomalies(null);
    setNextActions(null);
    setActionOutcomes(null);
    setPersonaDash(null);
    setPersonaError("");
  }

  async function handleResetDemo() {
    setResettingDemo(true);
    setError("");
    try {
      await resetDemoData();
      await loadTasks();
      await loadInsights();
      await loadPlayback(playbackPresetDays);
      await loadPersonaDashboard(personaRole);
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
      await loadPlayback(playbackPresetDays);
      await loadPersonaDashboard(personaRole);
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
      await loadPlayback(playbackPresetDays);
      setAiNote(`Created ${roadmapTasks.length} roadmap task(s).`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not create roadmap tasks");
    } finally {
      setAiCreateRoadmapLoading(false);
    }
  }

  async function handleExplainInsight(
    insightId: string,
    query?: { days?: number; baseline_days?: number },
  ) {
    setExplainingInsightId(insightId);
    setError("");
    try {
      const data = await getInsightExplanation(insightId, query);
      setInsightExplanations((prev) => ({ ...prev, [insightId]: data }));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load insight explanation");
    } finally {
      setExplainingInsightId(null);
    }
  }

  async function handleNextActionOutcome(feedbackKey: string, outcome: NextActionOutcome) {
    setUpdatingNextActionKey(feedbackKey);
    setError("");
    try {
      await recordNextActionOutcome(feedbackKey, outcome);
      await loadInsights();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not update next-action outcome");
    } finally {
      setUpdatingNextActionKey(null);
    }
  }

  async function handleApplyNextAction(feedbackKey: string) {
    setApplyingNextActionKey(feedbackKey);
    setError("");
    try {
      await applyNextAction(feedbackKey);
      await loadTasks();
      await loadInsights();
      await loadPlayback(playbackPresetDays);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not apply next action");
    } finally {
      setApplyingNextActionKey(null);
    }
  }

  async function handleAgentPreview() {
    if (!agentQuery.trim()) return;
    setAgentLoading(true);
    setError("");
    try {
      const response = await runAgentCommand(agentQuery.trim(), true);
      setAgentActions(response.actions ?? []);
      setAgentMessage(response.assistant_message || "Preview generated.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not preview AI command");
    } finally {
      setAgentLoading(false);
    }
  }

  async function handleAgentExecute() {
    if (!agentQuery.trim()) return;
    setAgentExecuting(true);
    setError("");
    try {
      const response = await runAgentCommand(agentQuery.trim(), false);
      setAgentActions(response.actions ?? []);
      setAgentMessage(response.assistant_message || "Command executed.");
      await loadTasks();
      await loadInsights();
      await loadPlayback(playbackPresetDays);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not execute AI command");
    } finally {
      setAgentExecuting(false);
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

                <h3 className="persona-heading">Recruiter persona views</h3>
                <p className="muted">
                  Same underlying tasks; cards switch between operational (manager), analytical (analyst),
                  and strategic (executive) lenses.
                </p>
                <div className="task-actions persona-toolbar">
                  <label>
                    View as
                    <select
                      value={personaRole}
                      onChange={(e) => setPersonaRole(e.target.value as PersonaRole)}
                      disabled={personaLoading}
                    >
                      <option value="manager">Manager — operational</option>
                      <option value="analyst">Analyst — metrics</option>
                      <option value="executive">Executive — strategic</option>
                    </select>
                  </label>
                  <button
                    type="button"
                    onClick={() => void loadPersonaDashboard(personaRole)}
                    disabled={personaLoading}
                  >
                    {personaLoading ? "Loading..." : "Refresh view"}
                  </button>
                </div>
                {personaError ? <p className="error">{personaError}</p> : null}
                {personaLoading && !personaDash ? <p className="muted">Loading persona dashboard…</p> : null}
                {personaDash ? (
                  <div className="persona-dashboard">
                    <p className="muted">{personaDash.tagline}</p>
                    <p className="persona-meta muted">
                      <span>{personaDash.lens}</span>
                      <span>·</span>
                      <span>{personaDash.shared.task_total} tasks</span>
                      <span>·</span>
                      <span>overdue open {personaDash.shared.overdue_open_total}</span>
                    </p>
                    {personaDash.headline ? (
                      <p>
                        <strong>{personaDash.headline}</strong>
                      </p>
                    ) : null}
                    {personaDash.cards.map((c) => (
                      <div key={c.id} className="insight-block">
                        <strong>{c.title}</strong>
                        <PersonaCardBlock card={c} />
                      </div>
                    ))}
                    {personaDash.action_queue && personaDash.action_queue.length > 0 ? (
                      <div className="insight-block">
                        <strong>Action queue</strong>
                        <ul className="simple-list">
                          {personaDash.action_queue.map((a) => (
                            <li key={a.task_id}>
                              {a.title} ({a.priority}) — {a.hours_overdue}h overdue
                            </li>
                          ))}
                        </ul>
                      </div>
                    ) : null}
                  </div>
                ) : !personaLoading && !personaError ? (
                  <p className="muted">Persona data will load when demo mode is enabled on the API.</p>
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

          <section className="panel">
            <h2>AI Command Console</h2>
            <p className="muted">
              Ask AI to create, update, or delete tasks. Preview first, then execute.
            </p>
            <div className="task-form">
              <textarea
                value={agentQuery}
                onChange={(e) => setAgentQuery(e.target.value)}
                placeholder='Example: "Create a task to publish release notes tomorrow 5pm, then mark task 12 done"'
              />
              <div className="task-actions">
                <button type="button" onClick={() => void handleAgentPreview()} disabled={agentLoading}>
                  {agentLoading ? "Previewing..." : "Preview tool calls"}
                </button>
                <button
                  type="button"
                  onClick={() => void handleAgentExecute()}
                  disabled={agentExecuting || agentLoading}
                >
                  {agentExecuting ? "Executing..." : "Confirm and execute"}
                </button>
              </div>
              {agentMessage ? <p className="muted">{agentMessage}</p> : null}
              {agentActions.length > 0 ? (
                <ul className="simple-list">
                  {agentActions.map((action, idx) => (
                    <li key={`${action.tool}-${idx}`}>
                      <strong>{action.tool}</strong>: {action.ok ? "ok" : "failed"}
                      {action.task_id ? ` (task #${action.task_id})` : ""}
                      {action.detail ? ` - ${action.detail}` : ""}
                      {action.task_preview ? ` - ${action.task_preview.title}` : ""}
                    </li>
                  ))}
                </ul>
              ) : null}
            </div>
          </section>

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
            <div className="list-head">
              <h2>KPI playback</h2>
              <button type="button" onClick={() => void loadPlayback(playbackPresetDays)} disabled={playbackLoading}>
                {playbackLoading ? "Refreshing..." : "Refresh playback"}
              </button>
            </div>
            <div className="task-actions">
              <button
                type="button"
                onClick={() => setPlaybackPresetDays(30)}
                disabled={playbackLoading || playbackPresetDays === 30}
              >
                Last 30 days
              </button>
              <button
                type="button"
                onClick={() => setPlaybackPresetDays(60)}
                disabled={playbackLoading || playbackPresetDays === 60}
              >
                Last 60 days
              </button>
              <button
                type="button"
                onClick={() => setPlaybackPresetDays(90)}
                disabled={playbackLoading || playbackPresetDays === 90}
              >
                Last 90 days
              </button>
            </div>
            {playbackError ? <p className="error">{playbackError}</p> : null}
            {playback?.snapshots?.length ? (
              <>
                <label>
                  Timeline
                  <input
                    type="range"
                    min={0}
                    max={Math.max(0, playback.snapshots.length - 1)}
                    value={playbackCursor}
                    onChange={(e) => setPlaybackCursor(Number(e.target.value))}
                    disabled={playbackLoading}
                  />
                </label>
                <div className="insight-block">
                  <small>
                    {new Date(playback.snapshots[playbackCursor].at).toLocaleDateString()} | point{" "}
                    {playbackCursor + 1}/{playback.snapshots.length}
                  </small>
                  <ul className="simple-list">
                    <li>
                      <strong>Completion:</strong> {playback.snapshots[playbackCursor].completion}
                    </li>
                    <li>
                      <strong>Overdue count:</strong> {playback.snapshots[playbackCursor].overdue_count}
                    </li>
                    <li>
                      <strong>Cycle time:</strong>{" "}
                      {playback.snapshots[playbackCursor].cycle_time_hours === null
                        ? "n/a"
                        : `${playback.snapshots[playbackCursor].cycle_time_hours}h`}
                    </li>
                  </ul>
                </div>
              </>
            ) : (
              <p className="muted">{playbackLoading ? "Loading timeline..." : "No playback data yet."}</p>
            )}
          </section>

          <section className="panel">
            <h2>Anomaly detection</h2>
            <p className="muted">
              Unusual spikes or drops in daily completions, overdue backlog, and cycle time vs a{" "}
              {anomalies?.baseline_days ?? 7}-day rolling baseline (last {anomalies?.window_days ?? 30}{" "}
              days). Sorted by impact.
            </p>
            <div className="task-actions">
              <button
                type="button"
                onClick={() =>
                  void handleExplainInsight("anomalies", {
                    days: anomalies?.window_days ?? 30,
                    baseline_days: anomalies?.baseline_days ?? 7,
                  })
                }
                disabled={explainingInsightId === "anomalies"}
              >
                {explainingInsightId === "anomalies" ? "Loading why..." : "Why this insight?"}
              </button>
            </div>
            {insightExplanations.anomalies ? (
              <div className="insight-block">
                <p>
                  <strong>{insightExplanations.anomalies.title}</strong>
                </p>
                <ul className="simple-list">
                  {insightExplanations.anomalies.why.map((item) => (
                    <li key={item}>{item}</li>
                  ))}
                </ul>
              </div>
            ) : null}
            {anomalies && anomalies.anomalies.length > 0 ? (
              <ul className="simple-list">
                {anomalies.anomalies.map((item) => (
                  <li key={item.id}>
                    <strong>
                      {item.metric === "completion"
                        ? "Completions"
                        : item.metric === "overdue_count"
                          ? "Overdue backlog"
                          : "Cycle time"}
                    </strong>{" "}
                    {item.direction} on {new Date(item.date).toLocaleDateString()} — value{" "}
                    <strong>{item.value}</strong> (baseline avg {item.baseline_mean}, z{" "}
                    {item.z_score}) · confidence <strong>{item.confidence}</strong> · impact{" "}
                    <strong>{item.impact}</strong>
                    <p className="muted">{item.likely_cause}</p>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="muted">
                {anomalies
                  ? "No strong anomalies in this window. Need more day-to-day variance or history."
                  : "Load insights to compute anomalies."}
              </p>
            )}
          </section>

          <section className="panel">
            <h2>Next best actions</h2>
            {nextActions ? (
              <div className="insight-block">
                <p>{nextActions.suggestion}</p>
                <small>candidates: {nextActions.total_candidates}</small>
                {nextActions.actions.length > 0 ? (
                  <ul className="simple-list">
                    {nextActions.actions.slice(0, 8).map((item) => (
                      <li key={item.id}>
                        <p>
                          <strong>{item.action_type}</strong> - {item.action}
                        </p>
                        <small>
                          task: {item.task_title} | overdue: {item.hours_overdue}h | score:{" "}
                          {item.rank_score} | learned x{item.learned_multiplier}
                        </small>
                        <div className="task-actions">
                          <button
                            type="button"
                            onClick={() => void handleApplyNextAction(item.feedback_key)}
                            disabled={applyingNextActionKey === item.feedback_key}
                          >
                            {applyingNextActionKey === item.feedback_key ? "applying..." : "apply now"}
                          </button>
                          <button
                            type="button"
                            onClick={() => void handleNextActionOutcome(item.feedback_key, "accepted")}
                            disabled={
                              updatingNextActionKey === item.feedback_key ||
                              applyingNextActionKey === item.feedback_key
                            }
                          >
                            accepted
                          </button>
                          <button
                            type="button"
                            onClick={() => void handleNextActionOutcome(item.feedback_key, "dismissed")}
                            disabled={
                              updatingNextActionKey === item.feedback_key ||
                              applyingNextActionKey === item.feedback_key
                            }
                          >
                            dismissed
                          </button>
                          <button
                            type="button"
                            onClick={() => void handleNextActionOutcome(item.feedback_key, "completed")}
                            disabled={
                              updatingNextActionKey === item.feedback_key ||
                              applyingNextActionKey === item.feedback_key
                            }
                          >
                            completed
                          </button>
                        </div>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="muted">No actionable overdue work right now.</p>
                )}
              </div>
            ) : (
              <p className="muted">Loading next actions...</p>
            )}
          </section>

          <section className="panel">
            <h2>Action outcome trends</h2>
            <p className="muted">
              Feedback you record on next-best actions (last {actionOutcomes?.window_days ?? 90} days) feeds ranking.
            </p>
            {actionOutcomes ? (
              <div className="insight-block">
                <p>{actionOutcomes.summary}</p>
                <small>
                  events: {actionOutcomes.totals.all} · accepted {actionOutcomes.totals.accepted} · dismissed{" "}
                  {actionOutcomes.totals.dismissed} · completed {actionOutcomes.totals.completed} · overall positive rate{" "}
                  {(actionOutcomes.totals.overall_positive_rate * 100).toFixed(1)}%
                </small>
                {Object.keys(actionOutcomes.by_action_type).length > 0 ? (
                  <table className="persona-table">
                    <thead>
                      <tr>
                        <th>Action type</th>
                        <th>Total</th>
                        <th>Accepted</th>
                        <th>Dismissed</th>
                        <th>Completed</th>
                        <th>Positive rate</th>
                      </tr>
                    </thead>
                    <tbody>
                      {Object.entries(actionOutcomes.by_action_type).map(([type, row]) => (
                        <tr key={type}>
                          <td>{type}</td>
                          <td>{row.total}</td>
                          <td>{row.accepted}</td>
                          <td>{row.dismissed}</td>
                          <td>{row.completed}</td>
                          <td>{(row.positive_rate * 100).toFixed(1)}%</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                ) : (
                  <p className="muted">No breakdown yet.</p>
                )}
                {actionOutcomes.recent.length > 0 ? (
                  <>
                    <strong>Recent feedback</strong>
                    <ul className="simple-list">
                      {actionOutcomes.recent.map((ev) => (
                        <li key={ev.id}>
                          <strong>{ev.action_type}</strong> → {ev.outcome}
                          {ev.created_at ? (
                            <span className="muted">
                              {" "}
                              ({new Date(ev.created_at).toLocaleString()})
                            </span>
                          ) : null}
                          <div className="muted">{ev.feedback_key}</div>
                        </li>
                      ))}
                    </ul>
                  </>
                ) : null}
              </div>
            ) : (
              <p className="muted">Loading outcome trends...</p>
            )}
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
            <div className="list-head">
              <h2>Insights snapshot</h2>
              <button type="button" onClick={() => void loadInsightsSnapshot()} disabled={snapshotLoading}>
                {snapshotLoading ? "Loading..." : "Load combined digest"}
              </button>
            </div>
            <p className="muted">
              One request merges productivity, overdue priority, KPI anomalies, and ranked next-actions
              (same logic as the individual insight endpoints).
            </p>
            {insightsSnapshot ? (
              <div className="insight-block">
                <p>
                  <strong>Productivity:</strong> {insightsSnapshot.productivity.narrative}
                </p>
                <p>
                  <strong>Priority:</strong> {insightsSnapshot.priority.suggestion} (overdue total{" "}
                  {insightsSnapshot.priority.total_overdue}, high in view{" "}
                  {insightsSnapshot.priority.high_priority_overdue_in_view})
                </p>
                <p>
                  <strong>Anomalies:</strong> {insightsSnapshot.anomalies.flagged_count} flag(s); window{" "}
                  {insightsSnapshot.anomalies.window_days}d, baseline {insightsSnapshot.anomalies.baseline_days}d
                  {insightsSnapshot.anomalies.top ? (
                    <>
                      {" "}
                      — top: {insightsSnapshot.anomalies.top.metric} {insightsSnapshot.anomalies.top.direction}{" "}
                      (impact {insightsSnapshot.anomalies.top.impact})
                    </>
                  ) : null}
                </p>
                <p>
                  <strong>Next actions:</strong> {insightsSnapshot.next_actions.suggestion} (
                  {insightsSnapshot.next_actions.total_candidates} candidate(s))
                </p>
                {insightsSnapshot.next_actions.top_ranked.length > 0 ? (
                  <ul className="simple-list">
                    {insightsSnapshot.next_actions.top_ranked.map((row) => (
                      <li key={row.feedback_key}>
                        <strong>{row.action_type}</strong> {row.task_title ?? ""} (score {row.rank_score})
                      </li>
                    ))}
                  </ul>
                ) : null}
              </div>
            ) : null}
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
