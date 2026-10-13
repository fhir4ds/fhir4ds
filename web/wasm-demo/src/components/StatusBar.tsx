export interface Metrics {
  translationTimeMs?: number;
  executionTimeMs?: number;
}

interface StatusBarProps {
  metrics: Metrics;
  message: string;
  isError: boolean;
  /** c-wasm-bolton S1: engine badge — "wasm" (standalone) or the connected
   *  server version; S2 P1: clickable popover with retry + override. */
  engineBadge?: string;
  workspaceName?: string;
  /** Popover content (connected): base URL + capability summary. */
  engineBase?: string;
  onRetry?: () => void;
  onUseStandalone?: () => void;
}

import { useState } from "react";

export function StatusBar({ metrics, message, isError, engineBadge, workspaceName, engineBase, onRetry, onUseStandalone }: StatusBarProps) {
  const [popoverOpen, setPopoverOpen] = useState(false);
  const connected = engineBadge !== undefined && engineBadge !== "wasm" && engineBadge !== "…";
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
        <>
          <button
            type="button"
            className="metric status-engine"
            aria-expanded={popoverOpen}
            aria-label={
              engineBadge === "wasm"
                ? "In-browser engine (standalone)"
                : `Connected server ${engineBadge} — engine options`
            }
            onClick={() => connected && setPopoverOpen((v) => !v)}
            onKeyDown={(e) => {
              if (connected && e.key === "Escape") setPopoverOpen(false);
            }}
          >
            {engineBadge === "wasm" ? "⚙ wasm" : engineBadge === "…" ? "⚙ …" : `🖧 server ${engineBadge}`}
          </button>
          {popoverOpen && connected && (
            <div className="engine-popover" role="dialog" aria-label="Engine options">
              <h4>Engine</h4>
              <dl>
                <dt>mode</dt>
                <dd>connected</dd>
                <dt>server</dt>
                <dd>{engineBadge}</dd>
                {engineBase && (<><dt>base</dt><dd>{engineBase}</dd></>)}
                {workspaceName && (<><dt>workspace</dt><dd>{workspaceName}</dd></>)}
              </dl>
              <div className="engine-actions">
                <button type="button" onClick={() => { setPopoverOpen(false); onRetry?.(); }}>
                  Retry connection
                </button>
                <button type="button" onClick={() => { setPopoverOpen(false); onUseStandalone?.(); }}>
                  Use in-browser engine
                </button>
              </div>
            </div>
          )}
        </>
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
