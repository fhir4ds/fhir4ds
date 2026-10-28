import { useEffect, useState } from "react";

/**
 * S29: persistent app footer (status bar).
 *
 * One place for the three things that used to be scattered:
 *  - WHERE content lives: connected = local files (dev server), standalone
 *    = browser memory (IndexedDB autosave). Replaces the header workspace
 *    chip and the ambiguous "on disk / in memory" notes elsewhere.
 *  - WHAT just happened: the transient status/error note (previously a 6s
 *    flash in the header) persists here until replaced or dismissed; the
 *    "data files changed" hint rides here as a warning with its restart
 *    action instead of shifting the main layout.
 *  - HOW it runs: engine chip (server DuckDB vs browser WASM) + last-saved
 *    stamp + the version badge (moved out of the header).
 */

export interface StatusBarProps {
  connected: boolean;
  workspace: string | null;
  engine: string | null;
  /** Epoch ms of the last content save (standalone autosave / explicit
   *  writes); null when nothing has been saved this session. */
  lastSavedAt: number | null;
  /** Connected workspaces read from disk — nothing is written back, so
   *  the saved stamp explains the dash instead of lying. */
  diskSource: boolean;
  note: string | null;
  onDismissNote: () => void;
  dataHint: boolean;
  onRestartKernel: () => void;
  version: string | null;
}

function relTime(ts: number, now: number): string {
  const s = Math.max(0, Math.round((now - ts) / 1000));
  if (s < 5) return "just now";
  if (s < 60) return `${s}s ago`;
  const m = Math.round(s / 60);
  if (m < 60) return `${m}m ago`;
  const h = Math.round(m / 60);
  if (h < 24) return `${h}h ago`;
  return new Date(ts).toLocaleDateString();
}

export function StatusBar({
  connected,
  workspace,
  engine,
  lastSavedAt,
  diskSource,
  note,
  onDismissNote,
  dataHint,
  onRestartKernel,
  version,
}: StatusBarProps) {
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 20_000);
    return () => clearInterval(t);
  }, []);

  const engineLabel =
    engine ?? (connected ? "DuckDB" : "DuckDB-WASM");
  const savedLabel =
    lastSavedAt != null
      ? `saved ${relTime(lastSavedAt, now)}`
      : diskSource
        ? "local files"
        : "not saved yet";

  return (
    <footer className="app-footer" data-testid="status-bar">
      <span
        className="footer-loc"
        data-testid="footer-location"
        title={
          connected
            ? "Connected dev server — content is read from local files"
            : "Standalone — content lives in this browser (IndexedDB autosave)"
        }
      >
        {connected ? "📁" : "🧠"}{" "}
        {connected ? (workspace ?? "workspace") : "Browser workspace"}
        <span className="footer-dim">
          {" "}
          · {connected ? "local files" : "in memory"}
        </span>
      </span>

      <span className="footer-status">
        {dataHint && (
          <span className="footer-warn" data-testid="footer-data-hint">
            data files changed — kernel keeps loaded data
            <button
              type="button"
              className="link-btn"
              data-testid="footer-restart-kernel"
              onClick={onRestartKernel}
            >
              restart kernel
            </button>
          </span>
        )}
        {note && (
          <span
            className="footer-note status-note"
            data-testid="status-note"
            role="status"
          >
            {note}
            <button
              type="button"
              className="footer-dismiss"
              data-testid="status-note-dismiss"
              aria-label="dismiss"
              onClick={onDismissNote}
            >
              ×
            </button>
          </span>
        )}
      </span>

      <span className="footer-right">
        <span
          className="footer-dim"
          data-testid="footer-saved"
          title={
            diskSource
              ? "Content is read from local files; edits live in this session (File > Save exports a package)"
              : "Last browser autosave"
          }
        >
          {savedLabel}
        </span>
        <span className="footer-engine" data-testid="footer-engine">
          {engineLabel}
        </span>
        {version && (
          <span className="version-badge" data-testid="footer-version">
            {version}
          </span>
        )}
      </span>
    </footer>
  );
}
