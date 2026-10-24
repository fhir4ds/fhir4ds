import { useEffect, useMemo, useRef, useState } from "react";
import type { FlattenViewResult } from "../lib/protocol";
import { workerRequest } from "./BootOverlay";
import {
  buildDerivedView,
  deriveViewColumns,
  orphanedOverrides,
  type ViewOverrides,
} from "../lib/viewDerivation";
import { Spinner } from "./Spinner";

/**
 * ViewPane v2 — the View drawer inside Results (§3.5).
 *
 * ViewDefinitions run over the MeasureReports produced by the CQL
 * engine (evaluate → measure_report_from_rows), never raw dataset
 * resources. Default mode: VD DERIVED from the Measure (one integer
 * count column per population, forEach group) with fork-on-edit
 * per-column overrides (ghost-text defaults, keyed by normalized
 * population code). Custom mode: paste any MeasureReport VD.
 */

export function ViewPane({
  measure,
  measureReports,
  viewConfig,
  onViewConfigChange,
  onSql,
  onResult,
  recalcMs = 2000,
  initialVd,
  connected = false,
  reportsPending = false,
  onBusy,
}: {
  measure: Record<string, unknown> | null;
  measureReports: Array<Record<string, unknown>> | null;
  viewConfig: ViewOverrides | null;
  onViewConfigChange: (v: ViewOverrides) => void;
  /** Reports the flatten SQL upward (Results Show-SQL context). */
  onSql?: (sql: string | null) => void;
  /** Reports the flatten RESULT upward — Results renders the Output pane. */
  onResult?: (r: FlattenViewResult | null) => void;
  /** REORG 6e: auto-recalc delay (settings); 0 disables auto-run. */
  recalcMs?: number;
  /** S27: a session-imported ViewDefinition (nav Views > disk VD click)
   *  — the pane boots in Custom mode with this text and runs it over the
   *  session MeasureReports (same source as the derived view). */
  initialVd?: Record<string, unknown> | null;
  /** S31: connected = server-side flatten (/api/view/run with explicit
   *  resources) — no in-browser engine boot. */
  connected?: boolean;
  /** S32: the first heartbeat has not produced MeasureReports yet —
   *  show a spinner rather than flashing the no-reports hint. */
  reportsPending?: boolean;
  /** S32: reports the flatten busy state upward (console output spinner). */
  onBusy?: (busy: boolean) => void;
}) {
  const overrides = viewConfig ?? {};
  const columns = useMemo(
    () => deriveViewColumns(measure, overrides),
    [measure, overrides],
  );
  const orphans = useMemo(
    () => orphanedOverrides(measure, overrides),
    [measure, overrides],
  );
  const [mode, setMode] = useState<"derived" | "custom">(
    initialVd ? "custom" : "derived",
  );
  const [customVd, setCustomVd] = useState(
    initialVd ? JSON.stringify(initialVd, null, 2) : "",
  );
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const setOverride = (key: string, patch: { name?: string; path?: string }) => {
    const next: ViewOverrides = {
      ...overrides,
      [key]: { ...overrides[key], ...patch },
    };
    onViewConfigChange(next);
  };

  // U6: NO manual Run — the view recomputes after the reports or VD
  // config change (settings recalc delay; 0 = off), whenever there are
  // MeasureReports to flatten.
  const busyRef = useRef(false);
  const canAutoRun = (measureReports?.length ?? 0) > 0 && recalcMs > 0;
  useEffect(() => {
    if (!canAutoRun) return;
    const t = setTimeout(() => {
      if (busyRef.current) return;
      void run();
    }, recalcMs);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [measureReports, mode, customVd, overrides, canAutoRun, recalcMs]);

  async function run() {
    busyRef.current = true;
    setBusy(true);
    onBusy?.(true);
    setError(null);
    try {
      const viewDefinition =
        mode === "derived"
          ? buildDerivedView(measure, overrides)
          : JSON.parse(customVd || "null");
      const resources = measureReports ?? [];
      // S31: CONNECTED = server-side flatten over the session reports
      // (/api/view/run accepts explicit `resources`) — no Pyodide boot on
      // the connected path. Standalone keeps the in-browser worker.
      let env: FlattenViewResult;
      if (connected) {
        const res = await fetch("/api/view/run", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            text: JSON.stringify(viewDefinition),
            resources,
          }),
        });
        const body = (await res.json()) as {
          data?: FlattenViewResult;
        } & FlattenViewResult;
        env = (body?.data ?? body) as FlattenViewResult;
      } else {
        const resp = await workerRequest({
          type: "flatten_view",
          view_definition: viewDefinition,
          resources,
        });
        env = JSON.parse((resp as { envelope: string }).envelope);
      }
      onSql?.(env.ok ? (env.sql ?? null) : null);
      onResult?.(env.ok ? env : null);
      if (!env.ok) {
        setError(env.diagnostics?.map((d) => d.message).join("; ") ?? "view failed");
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      onResult?.(null);
    } finally {
      busyRef.current = false;
      setBusy(false);
      onBusy?.(false);
    }
  }

  return (
    <section className="pane view-pane" data-testid="view-pane">
      <header className="pane-header">
        <div className="pane-actions">
          {busy && (
            <span className="pane-meta" data-testid="view-busy">
              <Spinner label="running view" />
            </span>
          )}
          {/* S29: the SAME switch widget as the Builder/Cells toggles —
              Form ("From Measure") ⇄ Text (the VD editor). aria-checked
              tracks TEXT mode. */}
          <button
            type="button"
            className={`drawer-toggle mode-switch${mode === "custom" ? " on" : ""}`}
            data-testid="view-mode"
            role="switch"
            aria-label="View editor mode (form or text)"
            aria-checked={mode === "custom"}
            title={
              mode === "custom"
                ? "Switch to the From Measure form editor"
                : "Switch to the ViewDefinition text editor"
            }
            onClick={() => setMode(mode === "custom" ? "derived" : "custom")}
          >
            {mode === "custom" ? "Form ⇄" : "Text ⇄"}
          </button>
        </div>
      </header>
      {error && (
        <div className="pane-error" data-testid="view-error">
          {error}
        </div>
      )}
      {!(measureReports?.length) &&
        (reportsPending ? (
          <p className="pane-hint" data-testid="view-reports-loading">
            <Spinner label="waiting for MeasureReports" />
          </p>
        ) : (
          <p className="pane-hint" data-testid="view-no-reports">
            No MeasureReports yet — run an evaluation with a Measure mapping
            first.
          </p>
        ))}
      {orphans.length > 0 && (
        <div className="orphan-note" data-testid="view-orphans">
          {orphans.length} override(s) no longer match a population:
          {" "}
          <code>{orphans.join(", ")}</code>
          {" "}
          <button
            className="link-btn"
            data-testid="view-orphans-clear"
            onClick={() => {
              const live = new Set(columns.map((c) => c.key));
              const next: ViewOverrides = {};
              for (const k of Object.keys(overrides)) {
                if (live.has(k)) next[k] = overrides[k];
              }
              onViewConfigChange(next);
            }}
          >
            clean up
          </button>
        </div>
      )}
      {mode === "derived" ? (
        <div className="vd-config" data-testid="view-derived">
          {columns.length === 0 && (
            <p className="pane-hint" data-testid="view-no-columns">
              No populations yet — author them in the Measure pane.
            </p>
          )}
          <table className="vd-columns" data-testid="view-columns">
            <thead>
              <tr>
                <th>Column</th>
                <th>FHIRPath</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td>
                  <code>patient_id</code>
                  <span className="vd-base">base</span>
                </td>
                <td>
                  <code>%resource.subject.reference</code>
                </td>
              </tr>
              {columns.map((c) => (
                <tr key={c.key} data-testid={`view-col-${c.key}`}>
                  <td>
                    <input
                      value={overrides[c.key]?.name ?? ""}
                      placeholder={c.defaultName}
                      onChange={(e) => setOverride(c.key, { name: e.target.value })}
                      data-testid={`view-col-name-${c.key}`}
                    />
                    {c.overridden && (
                      <span className="vd-override-badge">overridden</span>
                    )}
                  </td>
                  <td>
                    <input
                      className="vd-path-input"
                      value={overrides[c.key]?.path ?? ""}
                      placeholder={c.defaultPath}
                      onChange={(e) => setOverride(c.key, { path: e.target.value })}
                      data-testid={`view-col-path-${c.key}`}
                    />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <textarea
          className="vd-editor"
          data-testid="vd-editor"
          value={customVd}
          onChange={(e) => setCustomVd(e.target.value)}
          placeholder='{"resource": "Patient", "select": [...]}'
          spellCheck={false}
        />
      )}
    </section>
  );
}
