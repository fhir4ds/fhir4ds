import { useMemo, useState } from "react";
import type { FlattenViewResult } from "../lib/protocol";
import { workerRequest } from "./BootOverlay";
import {
  buildDerivedView,
  deriveViewColumns,
  orphanedOverrides,
  type ViewOverrides,
} from "../lib/viewDerivation";

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
}: {
  measure: Record<string, unknown> | null;
  measureReports: Array<Record<string, unknown>> | null;
  viewConfig: ViewOverrides | null;
  onViewConfigChange: (v: ViewOverrides) => void;
  /** Reports the flatten SQL upward (Results Show-SQL context). */
  onSql?: (sql: string | null) => void;
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
  const [mode, setMode] = useState<"derived" | "custom">("derived");
  const [customVd, setCustomVd] = useState("");
  const [result, setResult] = useState<FlattenViewResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const setOverride = (key: string, patch: { name?: string; path?: string }) => {
    const next: ViewOverrides = {
      ...overrides,
      [key]: { ...overrides[key], ...patch },
    };
    onViewConfigChange(next);
  };

  async function run() {
    setBusy(true);
    setError(null);
    try {
      const viewDefinition =
        mode === "derived"
          ? buildDerivedView(measure, overrides)
          : JSON.parse(customVd || "null");
      const resources = measureReports ?? [];
      const resp = await workerRequest({
        type: "flatten_view",
        view_definition: viewDefinition,
        resources,
      });
      const env: FlattenViewResult = JSON.parse(
        (resp as { envelope: string }).envelope,
      );
      setResult(env);
      onSql?.(env.ok ? (env.sql ?? null) : null);
      if (!env.ok) {
        setError(env.diagnostics?.map((d) => d.message).join("; ") ?? "view failed");
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  const outColumns = result?.ok ? result.columns : [];
  const rows = result?.ok ? result.rows : [];

  return (
    <section className="pane" data-testid="view-pane">
      <header className="pane-header">
        <h2>View</h2>
        <div className="pane-actions">
          <select
            value={mode}
            onChange={(e) => setMode(e.target.value as "derived" | "custom")}
            data-testid="view-mode"
          >
            <option value="derived">From Measure</option>
            <option value="custom">Custom VD</option>
          </select>
          <button onClick={run} disabled={busy} data-testid="view-run">
            {busy ? "Running…" : "Run view"}
          </button>
        </div>
      </header>
      {error && (
        <div className="pane-error" data-testid="view-error">
          {error}
        </div>
      )}
      {!(measureReports?.length) && (
        <p className="pane-hint" data-testid="view-no-reports">
          No MeasureReports yet — run an evaluation with a Measure mapping
          first.
        </p>
      )}
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
      {result?.ok && (
        <div className="view-result" data-testid="view-result">
          <div className="sql-summary" data-testid="view-sql">
            {outColumns.length} column(s), {rows.length} row(s)
          </div>
          <table className="result-table" data-testid="view-table">
            <thead>
              <tr>
                {outColumns.map((c) => (
                  <th key={c}>{c}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((r, i) => (
                <tr key={i}>
                  {outColumns.map((c) => (
                    <td key={c}>{r[c] === null || r[c] === undefined ? "—" : String(r[c])}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
