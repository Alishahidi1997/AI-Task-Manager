import { useCallback, useEffect, useState } from "react";
import {
  getAuditDetail,
  listAuditLogs,
  type AuditDetail,
  type AuditListItem,
} from "../api";

type AuditPanelProps = {
  enabled: boolean;
};

function formatWhen(value: string): string {
  try {
    return new Date(value).toLocaleString();
  } catch {
    return value;
  }
}

function truncate(text: string, max = 72): string {
  const trimmed = text.trim();
  return trimmed.length > max ? `${trimmed.slice(0, max)}…` : trimmed;
}

export function AuditPanel({ enabled }: AuditPanelProps) {
  const [items, setItems] = useState<AuditListItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [detail, setDetail] = useState<AuditDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);

  const loadList = useCallback(async () => {
    if (!enabled) return;
    setLoading(true);
    setError(null);
    try {
      const response = await listAuditLogs(50);
      setItems(response.items);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load audit log");
      setItems([]);
    } finally {
      setLoading(false);
    }
  }, [enabled]);

  useEffect(() => {
    void loadList();
  }, [loadList]);

  async function openDetail(auditId: number) {
    setSelectedId(auditId);
    setDetailLoading(true);
    setError(null);
    try {
      const row = await getAuditDetail(auditId);
      setDetail(row);
    } catch (err) {
      setDetail(null);
      setError(err instanceof Error ? err.message : "Could not load audit detail");
    } finally {
      setDetailLoading(false);
    }
  }

  if (!enabled) {
    return null;
  }

  return (
    <section className="panel audit-panel">
      <div className="list-head">
        <div>
          <h2>AI audit log</h2>
          <p className="muted">
            Orchestration outcomes for your workspace — validation, execution, and Slack traces.
          </p>
        </div>
        <button type="button" onClick={() => void loadList()} disabled={loading}>
          {loading ? "Refreshing…" : "Refresh"}
        </button>
      </div>

      {error ? <p className="error-text">{error}</p> : null}

      {items.length === 0 && !loading ? (
        <p className="muted">No orchestration events yet. Use chat or Slack to generate audit rows.</p>
      ) : (
        <ul className="simple-list audit-list">
          {items.map((item) => (
            <li key={item.id}>
              <button
                type="button"
                className="audit-row-button"
                onClick={() => void openDetail(item.id)}
                aria-pressed={selectedId === item.id}
              >
                <span className="audit-row-top">
                  <strong>#{item.id}</strong>
                  <span>{item.tool_name ?? "—"}</span>
                  <span>{item.validation_result}</span>
                  <span>{item.execution_result}</span>
                </span>
                <span className="muted">{formatWhen(item.created_at)}</span>
                <span className="muted">{truncate(item.request_text)}</span>
              </button>
            </li>
          ))}
        </ul>
      )}

      {selectedId != null ? (
        <div className="audit-detail">
          <h3>Audit #{selectedId}</h3>
          {detailLoading ? <p className="muted">Loading detail…</p> : null}
          {detail ? (
            <>
              <p>
                <strong>Tool:</strong> {detail.tool_name ?? "—"} ·{" "}
                <strong>Validation:</strong> {detail.validation_result} ·{" "}
                <strong>Execution:</strong> {detail.execution_result}
              </p>
              <p className="muted">{detail.request_text}</p>
              {detail.arguments ? (
                <pre className="audit-json">{detail.arguments}</pre>
              ) : null}
              {detail.trace ? (
                <div className="insight-why">
                  <p>
                    <strong>Slack trace</strong> {detail.trace.trace_id} · {detail.trace.outcome} ·{" "}
                    {detail.trace.total_duration_ms}ms
                  </p>
                  {detail.trace.spans.length > 0 ? (
                    <ul className="simple-list">
                      {detail.trace.spans.map((span, index) => (
                        <li key={`${detail.trace?.trace_id}-${index}`}>
                          {String(span.name ?? "span")}: {String(span.duration_ms ?? "?")}ms
                        </li>
                      ))}
                    </ul>
                  ) : null}
                </div>
              ) : (
                <p className="muted">No linked Slack trace for this audit row.</p>
              )}
            </>
          ) : null}
        </div>
      ) : null}
    </section>
  );
}
