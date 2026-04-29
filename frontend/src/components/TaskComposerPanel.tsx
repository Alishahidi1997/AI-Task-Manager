import type { FormEvent } from "react";

type TaskComposerPanelProps = {
  aiInput: string;
  aiLoading: boolean;
  aiPlanLoading: boolean;
  aiCreateRoadmapLoading: boolean;
  aiNote: string;
  roadmapTitle: string;
  roadmapMode: string;
  roadmapReason: string;
  roadmapTasks: Array<{
    order: number;
    title: string;
    description: string | null;
    due_date: string | null;
    category: string;
    priority: "low" | "medium" | "high";
  }>;
  title: string;
  description: string;
  dueDate: string;
  creating: boolean;
  onAiInputChange: (value: string) => void;
  onAiParse: () => Promise<void>;
  onAiPlan: () => Promise<void>;
  onCreateRoadmapTasks: () => Promise<void>;
  onSubmit: (e: FormEvent<HTMLFormElement>) => Promise<void>;
  onTitleChange: (value: string) => void;
  onDescriptionChange: (value: string) => void;
  onDueDateChange: (value: string) => void;
};

export function TaskComposerPanel({
  aiInput,
  aiLoading,
  aiPlanLoading,
  aiCreateRoadmapLoading,
  aiNote,
  roadmapTitle,
  roadmapMode,
  roadmapReason,
  roadmapTasks,
  title,
  description,
  dueDate,
  creating,
  onAiInputChange,
  onAiParse,
  onAiPlan,
  onCreateRoadmapTasks,
  onSubmit,
  onTitleChange,
  onDescriptionChange,
  onDueDateChange,
}: TaskComposerPanelProps) {
  return (
    <>
      <section className="panel">
        <h2>AI task parser</h2>
        <p className="muted">Write a natural sentence and auto-fill the form below.</p>
        <div className="task-form">
          <textarea
            value={aiInput}
            onChange={(e) => onAiInputChange(e.target.value)}
            placeholder='Example: "Finish auth docs tomorrow at 5pm and prepare release notes"'
          />
          <button type="button" onClick={() => void onAiParse()} disabled={aiLoading}>
            {aiLoading ? "Parsing..." : "Parse with AI"}
          </button>
          <button type="button" onClick={() => void onAiPlan()} disabled={aiPlanLoading}>
            {aiPlanLoading ? "Planning..." : "Break into roadmap"}
          </button>
          {aiNote ? <p className="muted">{aiNote}</p> : null}
          {roadmapTasks.length > 0 ? (
            <div className="insight-why">
              <p>
                <strong>{roadmapTitle}</strong> ({roadmapMode})
              </p>
              {roadmapReason ? <p className="muted">{roadmapReason}</p> : null}
              <ul className="simple-list">
                {roadmapTasks.map((task) => (
                  <li key={`${task.order}-${task.title}`}>
                    <strong>{task.order}. {task.title}</strong> [{task.category}, {task.priority}]
                  </li>
                ))}
              </ul>
              <button
                type="button"
                onClick={() => void onCreateRoadmapTasks()}
                disabled={aiCreateRoadmapLoading}
              >
                {aiCreateRoadmapLoading ? "Creating roadmap tasks..." : "Create all roadmap tasks"}
              </button>
            </div>
          ) : null}
        </div>
      </section>

      <section className="panel">
        <h2>Create task</h2>
        <form onSubmit={(e) => void onSubmit(e)} className="task-form">
          <label>
            Title
            <input
              value={title}
              onChange={(e) => onTitleChange(e.target.value)}
              placeholder="Finish API docs"
              required
            />
          </label>
          <label>
            Description
            <textarea
              value={description}
              onChange={(e) => onDescriptionChange(e.target.value)}
              placeholder="Optional details"
            />
          </label>
          <label>
            Due date
            <input
              type="datetime-local"
              value={dueDate}
              onChange={(e) => onDueDateChange(e.target.value)}
            />
          </label>
          <button type="submit" disabled={creating}>
            {creating ? "Creating..." : "Add task"}
          </button>
        </form>
      </section>
    </>
  );
}
