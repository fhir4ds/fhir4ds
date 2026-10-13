export interface Metrics {
  translationTimeMs?: number;
  executionTimeMs?: number;
}

interface StatusBarProps {
  metrics: Metrics;
  message: string;
  isError: boolean;
  /** c-wasm-bolton S1: engine badge — "wasm" (standalone) or the connected
   *  server version; clickable when connected (retry/override popover is
   *  S2 — S1 renders the badge + workspace name only). */
  engineBadge?: string;
  workspaceName?: string;
}

export function StatusBar({ metrics, message, isError, engineBadge, workspaceName }: StatusBarProps) {
  const total =
    (metrics.translationTimeMs ?? 0) + (metrics.executionTimeMs ?? 0);

  return (
    <footer className="status-bar">
      <span className={`status-message ${isError ? "error" : ""}`}>
        {message}
      </span>
      {workspaceName && (
        <span className="metric status-workspace" title="Connected workspace">
          {workspaceName}
        </span>
      )}
      {engineBadge && (
        <span
          className="metric status-engine"
          title={
            engineBadge === "wasm"
              ? "In-browser engine (standalone)"
              : `Connected server ${engineBadge}`
          }
        >
          {engineBadge === "wasm" ? "⚙ wasm" : `🖧 server ${engineBadge}`}
        </span>
      )}
      <div className="status-metrics">
        {metrics.translationTimeMs !== undefined && (
          <span className="metric">
            Translation: {metrics.translationTimeMs.toFixed(1)}ms
          </span>
        )}
        {metrics.executionTimeMs !== undefined && (
          <span className="metric">
            Execution: {metrics.executionTimeMs.toFixed(1)}ms
          </span>
        )}
        {total > 0 && (
          <span className="metric total">Total: {total.toFixed(1)}ms</span>
        )}
      </div>
    </footer>
  );
}
