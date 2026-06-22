import { useMemo, useState } from "react";
import type { FormEvent } from "react";
import {
  getOrCreateChatConversationId,
  resetChatConversationId,
  sendChatClarify,
  sendChatMessage,
  type ChatOrchestrationResult,
} from "../api";

type ChatMessage = {
  id: string;
  role: "user" | "assistant";
  text: string;
};

type ChatPanelProps = {
  onTasksChanged: () => void;
};

function formatChatResponse(body: ChatOrchestrationResult): string {
  if (body.status === "executed" && body.result) {
    const tool = body.planner_output?.tool_name ?? body.result.tool_name ?? "action";
    const taskId = body.result.task_id;
    const taskStatus = body.result.status;
    const assignee =
      typeof body.result.assignee === "string" ? body.result.assignee : null;
    const assigneeNote = assignee ? `, assignee: ${assignee}` : "";
    return `Done — ${tool}${taskId != null ? ` (task #${taskId}, ${taskStatus}${assigneeNote})` : ""}${body.audit_id != null ? ` [audit #${body.audit_id}]` : ""}.`;
  }
  if (body.status === "clarification_required") {
    return body.question ?? "I need more information to continue.";
  }
  if (body.status === "policy_rejected") {
    return `Policy blocked this request: ${body.reason ?? "not allowed"}`;
  }
  return `Status: ${body.status}${body.reason ? ` — ${body.reason}` : ""}`;
}

export function ChatPanel({ onTasksChanged }: ChatPanelProps) {
  const [conversationId, setConversationId] = useState(() => getOrCreateChatConversationId());
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [clarifyQuestion, setClarifyQuestion] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const conversationLabel = useMemo(
    () => (conversationId.length > 28 ? `${conversationId.slice(0, 28)}…` : conversationId),
    [conversationId],
  );

  async function handleOrchestrationResult(body: ChatOrchestrationResult) {
    const text = formatChatResponse(body);
    setMessages((prev) => [
      ...prev,
      { id: crypto.randomUUID(), role: "assistant", text },
    ]);
    if (body.status === "clarification_required") {
      setClarifyQuestion(body.question ?? "Please provide the missing details.");
      return;
    }
    setClarifyQuestion(null);
    if (body.status === "executed") {
      onTasksChanged();
    }
  }

  async function handleSend(e: FormEvent) {
    e.preventDefault();
    const text = input.trim();
    if (!text || loading) return;

    setError(null);
    setInput("");
    setMessages((prev) => [...prev, { id: crypto.randomUUID(), role: "user", text }]);
    setLoading(true);
    try {
      const body = clarifyQuestion
        ? await sendChatClarify(conversationId, text)
        : await sendChatMessage(text, conversationId);
      await handleOrchestrationResult(body);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Chat request failed");
    } finally {
      setLoading(false);
    }
  }

  function handleNewConversation() {
    const next = resetChatConversationId();
    setConversationId(next);
    setMessages([]);
    setClarifyQuestion(null);
    setError(null);
    setInput("");
  }

  return (
    <section className="panel chat-panel">
      <div className="list-head">
        <div>
          <h2>Chat orchestration</h2>
          <p className="muted">
            Planner + policy + execution via <code>POST /chat</code>. Queued mode auto-polls jobs.
          </p>
        </div>
        <button type="button" className="chat-new-thread" onClick={handleNewConversation}>
          New thread
        </button>
      </div>
      <p className="muted chat-thread-id">
        Conversation: <code>{conversationLabel}</code>
      </p>

      <div className="chat-thread" aria-live="polite">
        {messages.length === 0 ? (
          <p className="muted chat-empty">
            Try: &quot;Create a task due tomorrow called Release checklist&quot; then &quot;mark
            that done&quot;.
          </p>
        ) : (
          messages.map((msg) => (
            <div key={msg.id} className={`chat-bubble chat-bubble-${msg.role}`}>
              {msg.text}
            </div>
          ))
        )}
        {loading ? <p className="muted">Thinking…</p> : null}
      </div>

      {clarifyQuestion ? (
        <p className="chat-clarify-banner">
          <strong>Clarification needed:</strong> {clarifyQuestion}
        </p>
      ) : null}

      {error ? <p className="error-text">{error}</p> : null}

      <form className="task-form chat-form" onSubmit={(e) => void handleSend(e)}>
        <textarea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder={
            clarifyQuestion
              ? "Answer the clarification…"
              : 'Example: "Create a task called Sprint retro prep due Friday"'
          }
          disabled={loading}
        />
        <button type="submit" disabled={loading || !input.trim()}>
          {loading ? "Sending…" : clarifyQuestion ? "Send clarification" : "Send"}
        </button>
      </form>
    </section>
  );
}
