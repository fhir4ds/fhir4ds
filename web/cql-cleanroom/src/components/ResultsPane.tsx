import { useEffect, useRef, useState } from "react";
import type {
  EvaluateResult,
  Diagnostics,
  EvidenceResult,
  FlattenViewResult,
} from "../lib/protocol";
import { workerRequest } from "./BootOverlay";
import type { LibraryText } from "../lib/protocol";
import { AstTree } from "./AstPane";
import { EvidencePopover } from "./EvidencePopover";
import { PaginatedTable } from "./PaginatedTable";
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
  viewResult,
  parameters,
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
  viewResult: FlattenViewResult | null;
  parameters: Record<string, unknown> | null;
  reports: Array<Record<string, unknown>> | null;
  onEvaluated: (env: EvaluateResult) => void | Promise<void>;
}) {
  const [result, setResult] = useState<EvaluateResult | null>(null);
  const [diags, setDiags] = useState<Diagnostics[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [showSql, setShowSql] = useState(false);
  const [showAst, setShowAst] = useState(false);
  // Cell-level evidence drill-in: (patient, population) → explain.
  const [cellEvidence, setCellEvidence] = useState<{
    patientId: string;
    population: string;
    evidence: EvidenceResult | null;
  } | null>(null);

  async function explainCell(patientId: string, population: string) {
    setCellEvidence({ patientId, population, evidence: null });
    try {
      const resp = await workerRequest({
        type: "explain_patient",
        libraries,
        main,
        dataset,
        patient_id: patientId,
        parameters,
        output_columns: outputColumns,
      });
      const env: EvidenceResult = JSON.parse(resp.envelope);
      setCellEvidence((cur) =>
        cur && cur.patientId === patientId && cur.population === population
          ? { patientId, population, evidence: env }
          : cur,
      );
    } catch (e) {
      setCellEvidence({
        patientId,
        population,
        evidence: {
          schema: 1,
          ok: false,
          diagnostics: [
            {
              code: "evaluation_error" as const,
              severity: "error" as const,
              message: e instanceof Error ? e.message : String(e),
            },
          ],
          patient_id: patientId,
          populations: {},
          definitions: [],
        },
      });
    }
  }

  const populationColumns = (result?.columns ?? []).filter(
    (c) => c !== "patient_id",
  );

  // AUTO-EVALUATE: after the first run ATTEMPT (success or failure),
  // keep results live — recompute 2s after any input settles. Arming
  // on ANY attempt matters: a first run that fails on a missing
  // parameter must still arm, so filling the parameter auto-heals the
  // results without another manual click. Auto runs never record run
  // history (noise).
  const busyRef = useRef(false);
  // U5: NO manual Evaluate — evaluation auto-runs (2s debounce) whenever
  // the inputs change AND there is a dataset to evaluate against.
  const canAutoRun = !!dataset && !!main?.text;
  useEffect(() => {
    if (!canAutoRun) return;
    const t = setTimeout(() => {
      if (busyRef.current) return;
      void run(true);
    }, 2000);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [libraries, main, dataset, outputColumns, measure, parameters, canAutoRun]);

  const runSeq = useRef(0);
  async function run(recordRun = true) {
    const seq = ++runSeq.current;
    busyRef.current = true;
    setBusy(true);
    setDiags(null);
    try {
      const resp = await workerRequest({
        type: "evaluate_library",
        libraries,
        main,
        dataset,
        parameters,
        output_columns: outputColumns,
        emit_sql: true,
      });
      const env: EvaluateResult = JSON.parse(resp.envelope);
      if (seq !== runSeq.current) return; // superseded by a newer run
      if (env.ok) {
        env.evaluated_at = Date.now();
        setResult(env);
        if (recordRun) void onEvaluated(env);
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
      busyRef.current = false;
      setBusy(false);
    }
  }

  const tabs: Array<{ id: ResultsTab; label: string; testid: string }> = [
    { id: "cql", label: "CQL", testid: "results-tab-cql" },
    { id: "measure", label: "Measure Report", testid: "results-tab-measure" },
    { id: "view", label: "View Definition", testid: "results-tab-view" },
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
          {busy && (
            <span className="pane-meta" data-testid="run-busy">
              recalculating…
            </span>
          )}
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

      {/* CQL tab: Output pane (table + meta) first, Evidence drawer last */}
      <div className="tab-panel" hidden={activeTab !== "cql"} data-testid="tab-panel-cql">
        {result && (
          <div className="pane output-pane" data-testid="output-cql">
            <header className="pane-header">
              <h3>Output</h3>
            </header>
            <PaginatedTable
              testId="results-table"
              rowCount={result.rows.length}
              header={
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
              }
              renderRows={({ slice }) =>
                slice(result.rows).map((row) => {
                  const pid = String(row.patient_id ?? "");
                  return (
                    <tr key={pid}>
                      {result.columns.map((c) => {
                        const isPopulation =
                          c !== "patient_id" && row[c] !== undefined;
                        return (
                          <td
                            key={c}
                            className={
                              isPopulation ? "cell-evidence" : undefined
                            }
                            data-testid={
                              isPopulation ? `cell-${pid}-${c}` : undefined
                            }
                            title={
                              isPopulation ? `why: ${pid} · ${c}` : undefined
                            }
                            onClick={
                              isPopulation
                                ? () => void explainCell(pid, c)
                                : undefined
                            }
                          >
                            {renderValue(row[c])}
                          </td>
                        );
                      })}
                    </tr>
                  );
                })
              }
            />
            <div className="eval-meta" data-testid="eval-meta">
              {result.rows.length} rows · {result.columns.length} columns ·{" "}
              {result.evaluated_at
                ? `${new Date(result.evaluated_at).toLocaleString()} · `
                : ""}
              {result.timing_ms.evaluate}ms
            </div>
            {cellEvidence && (
              <EvidencePopover
                evidence={cellEvidence.evidence}
                patientId={cellEvidence.patientId}
                population={cellEvidence.population}
                onClose={() => setCellEvidence(null)}
              />
            )}
          </div>
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

      {/* MeasureReport tab: pivot table first, then Sankey, config drawers last */}
      <div className="tab-panel" hidden={activeTab !== "measure"} data-testid="tab-panel-measure">
        {reports && reports.length > 0 ? (
          <div className="pane output-pane" data-testid="mr-reports">
            <header className="pane-header">
              <h3>Output</h3>
            </header>
            <MrPivotTable reports={reports} />
            <MrMeta reports={reports} evaluatedAt={result?.evaluated_at} />
          </div>
        ) : (
          <p className="pane-hint" data-testid="mr-empty">
            {measure
              ? "Run an evaluation to materialize MeasureReports."
              : "Configure the Measure mapping, then re-evaluate."}
          </p>
        )}
        {result && populationColumns.length > 0 && (
          <div className="pane output-pane" data-testid="attrition-pane">
            <header className="pane-header">
              <h3>Attrition</h3>
            </header>
            <SankeyFromRows columns={populationColumns} rows={result.rows} />
          </div>
        )}
        {testsSlot}
        <div className="results-drawer" data-testid="drawer-populations">
          <details open>
            <summary className="drawer-toggle" data-testid="drawer-populations-toggle">
              Populations / Measure
            </summary>
            <div className="drawer-body">{measureSlot}</div>
          </details>
        </div>
      </div>

      {/* View Definition tab: Output pane (flatten results) first, VD config last */}
      <div className="tab-panel" hidden={activeTab !== "view"} data-testid="tab-panel-view">
        {viewResult?.ok && viewResult.columns.length > 0 && (
          <div className="pane output-pane" data-testid="output-view">
            <header className="pane-header">
              <h3>Output</h3>
            </header>
            <PaginatedTable
              testId="view-table"
              rowCount={viewResult.rows.length}
              header={
                <tr>
                  {viewResult.columns.map((c) => (
                    <th key={c}>{c}</th>
                  ))}
                </tr>
              }
              renderRows={({ slice }) =>
                slice(viewResult.rows).map((r, i) => (
                  <tr key={i}>
                    {viewResult.columns.map((c) => (
                      <td key="x">
                        {r[c] === null || r[c] === undefined
                          ? "—"
                          : String(r[c])}
                      </td>
                    ))}
                  </tr>
                ))
              }
            />
            <div className="eval-meta" data-testid="view-meta">
              {viewResult.rows.length} rows · {viewResult.columns.length} columns
            </div>
          </div>
        )}
        {viewSlot}
      </div>

      {activeSql && showSql && <SqlViewer sql={activeSql} />}
      {showAst && (
        <div className="pane output-pane" data-testid="ast-pane">
          <header className="pane-header">
            <h3>AST</h3>
          </header>
          <AstTree cqlText={main.text} />
        </div>
      )}
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
    <PaginatedTable
      testId="mr-table"
      rowCount={sortedPatients.length}
      header={
        <tr>
          <th>patient</th>
          {multiGroup && <th>group</th>}
          {codes.map((c) => (
            <th key={c}>{c}</th>
          ))}
        </tr>
      }
      renderRows={({ slice }) =>
        slice(sortedPatients).map((pid) => {
          const row = cells.get(pid)!;
          return (
            <tr key={pid} data-testid={`mr-row-${pid}`}>
              <td>{row.patient}</td>
              {multiGroup && <td>{row.gid}</td>}
              {codes.map((c) => (
                <td key={c}>{row.counts.get(c) ?? "—"}</td>
              ))}
            </tr>
          );
        })
      }
    />
  );
}

/** Meta line under the MR pivot table: rows · columns · timestamp. */
function MrMeta({
  reports,
  evaluatedAt,
}: {
  reports: Array<Record<string, unknown>>;
  evaluatedAt?: number;
}) {
  const cols = (reports[0] && (reports[0].group as Array<unknown>)?.length) ?? 0;
  return (
    <div className="eval-meta" data-testid="mr-meta">
      {reports.length} reports · {cols > 1 ? `${cols} groups · ` : ""}
      {evaluatedAt ? `${new Date(evaluatedAt).toLocaleString()}` : ""}
    </div>
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
