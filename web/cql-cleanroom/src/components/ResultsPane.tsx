import { useState } from "react";
import type { EvaluateResult, Diagnostics } from "../lib/protocol";
import { workerRequest } from "./BootOverlay";
import type { LibraryText } from "../lib/protocol";
import { AstTree } from "./AstPane";
import { PopulationSankey } from "./PopulationSankey";

/**
 * ResultsPane v3 (WORKBENCH_REORG §3.1) — three lenses on ONE run:
 * CQL output / MeasureReport output / ViewDefinition output. The
 * Evaluate button is shared; tabs never re-execute (INV-2). Config
 * is colocated: Measure config + Tests + rendered reports + the
 * single Sankey live in the MeasureReport tab; VD config + flatten
 * table in the ViewDefinition tab; Evidence drawer in the CQL tab.
 *
 * Show SQL / Show AST are header-level: SQL shows the SQL of what
 * the ACTIVE tab last executed (translation SQL for CQL + MR tabs;
 * flatten SQL for the View tab — the ViewPane reports it upward).
 * Inactive tabs stay mounted but hidden via .tab-panel[hidden]
 * (testids queryable, not actionable — specs click the tab first).
 */

export type ResultsTab = "cql" | "measure" | "view";

export function ResultsPane({
  libraries,
  main,
  dataset,
  outputColumns,
  measure,
  onReports,
  measureSlot,
  testsSlot,
  viewSlot,
  evidenceSlot,
  activeTab,
  onTabChange,
  viewSql,
  reports,
  onEvaluated,
}: {
  libraries: LibraryText[];
  main: LibraryText;
  dataset: { resources?: Record<string, unknown>[] } | null;
  outputColumns: Record<string, string> | null;
  measure: Record<string, unknown> | null;
  onReports: (reports: Array<Record<string, unknown>> | null) => void;
  measureSlot: React.ReactNode;
  testsSlot: React.ReactNode;
  viewSlot: React.ReactNode;
  evidenceSlot: React.ReactNode;
  activeTab: ResultsTab;
  onTabChange: (t: ResultsTab) => void;
  viewSql: string | null;
  reports: Array<Record<string, unknown>> | null;
  onEvaluated: (env: EvaluateResult) => void | Promise<void>;
}) {
  const [result, setResult] = useState<EvaluateResult | null>(null);
  const [diags, setDiags] = useState<Diagnostics[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [showSql, setShowSql] = useState(false);
  const [showAst, setShowAst] = useState(false);

  const populationColumns = (result?.columns ?? []).filter(
    (c) => c !== "patient_id",
  );

  async function run() {
    setBusy(true);
    setDiags(null);
    try {
      const resp = await workerRequest({
        type: "evaluate_library",
        libraries,
        main,
        dataset,
        output_columns: outputColumns,
        emit_sql: true,
      });
      const env: EvaluateResult = JSON.parse(resp.envelope);
      if (env.ok) {
        env.evaluated_at = Date.now();
        setResult(env);
        void onEvaluated(env);
        // Materialize per-patient MeasureReports from the evaluation
        // rows (feature point 3) — the MR tab's render source and the
        // View tab's default source.
        if (measure) {
          try {
            const repResp = await workerRequest({
              type: "measure_report_from_rows",
              measure,
              rows: env.rows,
              columns: env.columns,
            });
            const repEnv = JSON.parse((repResp as { envelope: string }).envelope) as {
              ok: boolean;
              reports?: Array<Record<string, unknown>>;
            };
            onReports(repEnv.ok ? repEnv.reports ?? [] : null);
          } catch {
            onReports(null);
          }
        } else {
          onReports(null);
        }
      } else {
        setDiags(env.diagnostics ?? []);
        onReports(null);
      }
    } finally {
      setBusy(false);
    }
  }

  const tabs: Array<{ id: ResultsTab; label: string; testid: string }> = [
    { id: "cql", label: "CQL output", testid: "results-tab-cql" },
    { id: "measure", label: "MeasureReport output", testid: "results-tab-measure" },
    { id: "view", label: "ViewDefinition output", testid: "results-tab-view" },
  ];

  const activeSql = activeTab === "view" ? viewSql : (result?.sql ?? null);

  return (
    <section className="pane" data-testid="results-pane">
      <header className="pane-header">
        <h2>Results</h2>
        <div className="pane-actions">
          <button
            onClick={() => setShowSql(!showSql)}
            disabled={!activeSql}
            data-testid="show-sql"
            title={
              activeTab === "view"
                ? "Flatten SQL for the last view run"
                : "Translation SQL for the last evaluation"
            }
          >
            {showSql ? "Hide SQL" : "Show SQL"}
          </button>
          <button onClick={() => setShowAst(!showAst)} data-testid="show-ast">
            {showAst ? "Hide AST" : "Show AST"}
          </button>
          <button onClick={run} disabled={busy} data-testid="run-eval">
            {busy ? "Running…" : "Evaluate"}
          </button>
        </div>
      </header>
      <div className="tab-strip results-tabs" data-testid="results-tabs">
        {tabs.map((t) => (
          <button
            key={t.id}
            className={`tab ${activeTab === t.id ? "active" : ""}`}
            data-testid={t.testid}
            onClick={() => onTabChange(t.id)}
          >
            {t.label}
          </button>
        ))}
      </div>

      {diags && (
        <ul className="diag-list" data-testid="eval-diags">
          {diags.map((d, i) => (
            <li key={i} className="diag-row">
              <span className="diag-code">{d.code}</span> {d.message}
            </li>
          ))}
        </ul>
      )}

      {/* CQL output tab: rows table + Evidence drawer */}
      <div className="tab-panel" hidden={activeTab !== "cql"} data-testid="tab-panel-cql">
        {result && (
          <>
            <div className="eval-meta" data-testid="eval-meta">
              {result.evaluated_at
                ? `${new Date(result.evaluated_at).toLocaleString()} · `
                : ""}
              {result.patient_count} patients · {result.timing_ms.evaluate}ms
            </div>
            <table className="results-table" data-testid="results-table">
              <thead>
                <tr>
                  {result.columns.map((c) => (
                    <th key={c}>
                      {c}
                      {result.column_types[c] && (
                        <span
                          className="type-badge"
                          data-testid={`type-badge-${c}`}
                          title="CQL type"
                        >
                          {result.column_types[c]}
                        </span>
                      )}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {result.rows.map((row, i) => (
                  <tr key={i}>
                    {result.columns.map((c) => (
                      <td key={c}>{renderValue(row[c])}</td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </>
        )}
        <div className="results-drawer" data-testid="drawer-evidence">
          <details open>
            <summary className="drawer-toggle" data-testid="drawer-evidence-toggle">
              Evidence
            </summary>
            <div className="drawer-body">{evidenceSlot}</div>
          </details>
        </div>
      </div>

      {/* MeasureReport tab: Measure config + Tests + reports + Sankey */}
      <div className="tab-panel" hidden={activeTab !== "measure"} data-testid="tab-panel-measure">
        <div className="results-drawer" data-testid="drawer-populations">
          <details open>
            <summary className="drawer-toggle" data-testid="drawer-populations-toggle">
              Populations / Measure
            </summary>
            <div className="drawer-body">{measureSlot}</div>
          </details>
        </div>
        {testsSlot}
        {reports && reports.length > 0 ? (
          <div className="mr-render" data-testid="mr-reports">
            <MrPivotTable reports={reports} />
          </div>
        ) : (
          <p className="pane-hint" data-testid="mr-empty">
            {measure
              ? "Run an evaluation to materialize MeasureReports."
              : "Configure the Measure mapping, then re-evaluate."}
          </p>
        )}
        {result && populationColumns.length > 0 && (
          <SankeyFromRows columns={populationColumns} rows={result.rows} />
        )}
      </div>

      {/* ViewDefinition tab: VD config + flatten table */}
      <div className="tab-panel" hidden={activeTab !== "view"} data-testid="tab-panel-view">
        {viewSlot}
      </div>

      {activeSql && showSql && <SqlViewer sql={activeSql} />}
      {showAst && <AstTree cqlText={main.text} />}
    </section>
  );
}

/**
 * Pivot the per-patient MeasureReports: one row per patient, one column
 * per population (matching the CQL tab's table shape). A group_id column
 * appears only when any report carries more than one group.
 */
function MrPivotTable({
  reports,
}: {
  reports: Array<Record<string, unknown>>;
}) {
  const multiGroup = reports.some(
    (r) => ((r.group as Array<unknown>) ?? []).length > 1,
  );
  // Ordered union of population codes + per-patient cell map, keyed
  // gid|code so multi-group reports keep columns distinct.
  const codes: string[] = [];
  const cells = new Map<
    string,
    { patient: string; gid: string; counts: Map<string, string> }
  >();
  for (const r of reports) {
    const subject =
      (r.subject as { reference?: string } | undefined)?.reference ?? "—";
    for (const g of (r.group as Array<Record<string, unknown>>) ?? []) {
      const gid = String(g.id ?? "");
      for (const p of (g.population as Array<Record<string, unknown>>) ?? []) {
        const code =
          ((p.code as { coding?: Array<{ code?: string }> })?.coding ?? [])[0]
            ?.code ?? "—";
        const col = multiGroup ? `${gid}:${code}` : code;
        if (!codes.includes(col)) codes.push(col);
        const key = subject;
        const entry = cells.get(key) ?? {
          patient: subject,
          gid,
          counts: new Map<string, string>(),
        };
        entry.counts.set(col, String(p.count ?? "—"));
        cells.set(key, entry);
      }
    }
  }
  const sortedPatients = [...cells.keys()].sort();
  return (
    <table className="results-table" data-testid="mr-table">
      <thead>
        <tr>
          <th>patient</th>
          {multiGroup && <th>group</th>}
          {codes.map((c) => (
            <th key={c}>{c}</th>
          ))}
        </tr>
      </thead>
      <tbody>
        {sortedPatients.map((pid, i) => {
          const row = cells.get(pid)!;
          return (
            <tr key={pid} data-testid={`mr-row-${i}`}>
              <td>{row.patient}</td>
              {multiGroup && <td>{row.gid}</td>}
              {codes.map((c) => (
                <td key={c}>{row.counts.get(c) ?? "—"}</td>
              ))}
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}

/** Sankey built inline from evaluation rows (single copy, MR tab). */
function SankeyFromRows({
  columns,
  rows,
}: {
  columns: string[];
  rows: Array<Record<string, unknown>>;
}) {
  return (
    <PopulationSankey
      data={{
        nodes: columns.map((name, i) => ({
          column: i,
          name,
          count: rows.filter((r) => r[name] === true).length,
        })),
        links: (() => {
          const links: Array<{ from: string; to: string; count: number }> = [];
          for (let i = 0; i < columns.length; i++) {
            for (let j = i + 1; j < columns.length; j++) {
              const a = columns[i];
              const b = columns[j];
              const both = rows.filter(
                (r) => r[a] === true && r[b] === true,
              ).length;
              if (both > 0) links.push({ from: a, to: b, count: both });
            }
          }
          return links;
        })(),
      }}
    />
  );
}

function renderValue(v: unknown): string {
  if (v === null || v === undefined) return "—";
  if (typeof v === "boolean") return v ? "true" : "false";
  if (typeof v === "object") return JSON.stringify(v);
  return String(v);
}

export function SqlViewer({ sql }: { sql: string }) {
  return (
    <div className="sql-viewer" data-testid="sql-viewer">
      <pre className="sql-pre">{sql}</pre>
    </div>
  );
}
