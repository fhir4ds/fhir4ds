export interface Metrics {
  translationTimeMs?: number;
  executionTimeMs?: number;
}

interface StatusBarProps {
  metrics: Metrics;
  message: string;
  isError: boolean;
}

export function StatusBar({ metrics, message, isError }: StatusBarProps) {
  const total =
    (metrics.translationTimeMs ?? 0) + (metrics.executionTimeMs ?? 0);

  return (
    <footer className="status-bar">
      <span className={`status-message ${isError ? "error" : ""}`}>
        {message}
      </span>
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
