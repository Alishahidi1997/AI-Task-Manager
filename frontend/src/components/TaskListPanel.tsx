import type { Task, TaskStatus } from "../api";

type TaskListPanelProps = {
  tasks: Task[];
  loading: boolean;
  error: string;
  updatingTaskId: number | null;
  deletingTaskId: number | null;
  onRefresh: () => Promise<void>;
  onStatusChange: (taskId: number, nextStatus: TaskStatus) => Promise<void>;
  onDeleteTask: (taskId: number) => Promise<void>;
};

export function TaskListPanel({
  tasks,
  loading,
  error,
  updatingTaskId,
  deletingTaskId,
  onRefresh,
  onStatusChange,
  onDeleteTask,
}: TaskListPanelProps) {
  return (
    <section className="panel">
      <div className="list-head">
        <h2>Tasks</h2>
        <button type="button" onClick={() => void onRefresh()} disabled={loading}>
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
              {task.assignee ? ` | assignee: ${task.assignee}` : ""}
            </small>
            <div className="task-actions">
              <select
                value={task.status}
                onChange={(e) => void onStatusChange(task.id, e.target.value as TaskStatus)}
                disabled={updatingTaskId === task.id}
              >
                <option value="todo">todo</option>
                <option value="in_progress">in_progress</option>
                <option value="done">done</option>
              </select>
              <button
                type="button"
                className="danger"
                onClick={() => void onDeleteTask(task.id)}
                disabled={deletingTaskId === task.id}
              >
                {deletingTaskId === task.id ? "Deleting..." : "Delete"}
              </button>
            </div>
          </li>
        ))}
      </ul>
    </section>
  );
}
