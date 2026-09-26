import { useEffect, useRef, useState } from "react";
import { workerRequest } from "./BootOverlay";
import { PaginatedTable } from "./PaginatedTable";
import { DiagnosticsRow } from "./EditorPane";
import { EvidencePopover } from "./EvidencePopover";
import { AstTree } from "./AstPane";
import { cellDiffClass } from "../lib/runDiff";
import { useRunDiff } from "./MeasureReportOutput";
import type {
  Diagnostics,
  LibraryText,
  DatasetSpec,
  EvaluateResult,
  EvidenceResult,
} from "../lib/protocol";
import type { Artifact } from "../lib/runDiff";

/**
 * WORKBENCH_REORG phase 5 — the CQL console below the editor, four
 * sub-tabs on one run pipeline:
 *   Results    — scratch output of Run / Run-Selection plus the live
 *                auto-evaluation table (cell evidence + run diff)
 *   SQL        — translation SQL of the last evaluation
 *   AST        — the parse tree of the visible library
 *   Diagnostics— evaluation diagnostics of the last run
 *
 * Run evaluates the WHOLE visible library; Run-Selection evaluates the
 * highlighted expression in context (worker evaluate_snippet: hidden
 * __snippet__ define, narrowed output, diagnostics renumbered back).
 *
 * A failing evaluation AUTO-SWITCHES the console to Diagnostics (and
 * back to Results once a run succeeds again) so errors announce
 * themselves without a click.
 */

export type ConsoleTab = "results" | "sql" | "ast" | "diags";

type ConsoleRows = {
  columns: string[];
  rows: Array<Record<string, unknown>>;
  ms: number | null;
};

const TABS: Array<{ id: ConsoleTab; label: string }> = [
  { id: "results", label: "Results" },
  { id: "sql", label: "SQL" },
  { id: "ast", label: "AST" },
  { id: "diags", label: "Diagnostics" },
];

export function ResultsConsole({
  libraries,
  main,
  dataset,
  parameters,
  outputColumns,
  selection,
  result,
  evalDiags,
  busy,
  baselineArtifact,
  activeTab,
  onTabChange,
}: {
  libraries: LibraryText[];
  main: LibraryText;
  dataset: DatasetSpec | null;
  parameters: Record<string, unknown>;
  outputColumns: Record<string, string> | null;
  /** Current editor selection text (null/empty disables Run-Selection). */
  selection: string | null;
  /** Live auto-evaluation of the entrypoint library (app heartbeat). */
  result: EvaluateResult | null;
  evalDiags: Diagnostics[] | null;
  busy: boolean;
  baselineArtifact: Artifact | null;
  activeTab: ConsoleTab;
  onTabChange: (t: ConsoleTab) => void;
}) {
  const [runBusy, setRunBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [diags, setDiags] = useState<Diagnostics[]>([]);
  const [scratch, setScratch] = useState<ConsoleRows | null>(null);
  const seqRef = useRef(0);

  // Error announce: on a NEW failing evaluation jump to Diagnostics;
  // when a run succeeds again, jump back (only if we auto-switched).
  const failSigRef = useRef("");
  const autoSwitchedRef = useRef(false);
  useEffect(() => {
    if (evalDiags && evalDiags.length > 0 && !busy) {
      const sig = JSON.stringify(evalDiags.map((d) => [d.code, d.message]));
      if (sig !== failSigRef.current) {
        failSigRef.current = sig;
        autoSwitchedRef.current = true;
        onTabChange("diags");
      }
    } else if (!evalDiags && result && autoSwitchedRef.current) {
      failSigRef.current = "";
      autoSwitchedRef.current = false;
      onTabChange("results");
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [evalDiags, result, busy]);

  const run = async (mode: "library" | "selection") => {
    const seq = ++seqRef.current;
    setRunBusy(true);
    setError(null);
    setDiags([]);
    try {
      const resp = await workerRequest(
        mode === "selection"
          ? {
              type: "evaluate_snippet",
              libraries,
              main,
              snippet: selection ?? "",
              dataset,
              parameters,
            }
          : {
              type: "evaluate_library",
              libraries,
              main,
              dataset,
              parameters,
              emit_sql: false,
            },
      );
      if (seq !== seqRef.current) return;
      const env = JSON.parse((resp as { envelope: string }).envelope) as {
        ok: boolean;
        diagnostics?: Diagnostics[];
        columns?: string[];
        rows?: Array<Record<string, unknown>>;
        timing_ms?: Record<string, number>;
      };
      if (!env.ok) {
        setDiags(env.diagnostics ?? []);
        setScratch(null);
      } else {
        setScratch({
          columns: env.columns ?? [],
          rows: env.rows ?? [],
          ms: env.timing_ms?.evaluate ?? null,
        });
      }
    } catch (e) {
      if (seq === seqRef.current) {
        setError(e instanceof Error ? e.message : String(e));
      }
    } finally {
      if (seq === seqRef.current) setRunBusy(false);
    }
  };

  // Cell-level evidence drill-in for the live results table.
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

  const hasSelection = (selection ?? "").trim().length > 0;
  const running = runBusy || busy;
  const runDiff = useRunDiff(result, baselineArtifact);

  return (
    <section className="pane results-console" data-testid="results-console">
      <header className="pane-header">
        <h2>CQL console</h2>
        <div className="pane-actions">
          <button
            data-testid="console-run-library"
            disabled={running}
            onClick={() => void run("library")}
          >
            {running ? "running…" : "Run"}
          </button>
          <button
            data-testid="console-run-selection"
            disabled={running || !hasSelection}
            title={hasSelection ? "evaluate the selected expression" : "select code in the editor first"}
            onClick={() => void run("selection")}
          >
            Run selection
          </button>
        </div>
      </header>
      <div className="tab-strip console-subtabs" data-testid="console-subtabs">
        {TABS.map((t) => (
          <button
            key={t.id}
            className={`tab ${activeTab === t.id ? "active" : ""}`}
            data-testid={`console-tab-${t.id}`}
            onClick={() => onTabChange(t.id)}
          >
            {t.label}
            {t.id === "diags" && evalDiags && evalDiags.length > 0
              ? ` (${evalDiags.length})`
              : ""}
          </button>
        ))}
      </div>

      <div
        className="tab-panel"
        hidden={activeTab !== "results"}
        data-testid="console-panel-results"
      >
        {error && <p className="pane-error" data-testid="console-error">{error}</p>}
        {diags.length > 0 && (
          <div className="diag-list" data-testid="console-diags">
            {diags.map((d, i) => (
              <DiagnosticsRow key={i} diag={d} />
            ))}
          </div>
        )}
        {scratch && scratch.columns.length > 0 && (
          <PaginatedTable
            testId="console-table"
            rowCount={scratch.rows.length}
            stats={
              <>
                {scratch.rows.length} rows ·{" "}
                {scratch.ms != null ? `${Math.round(scratch.ms)}ms` : ""}
              </>
            }
            header={
              <tr>
                <th>patient_id</th>
                {scratch.columns.filter((c) => c !== "patient_id").map((c) => (
                  <th key={c}>{c}</th>
                ))}
              </tr>
            }
            renderRows={(range) => (
              <>
                {scratch.rows.slice(range.start, range.end).map((r, i) => (
                  <tr key={range.start + i}>
                    <td>{String(r.patient_id ?? "")}</td>
                    {scratch.columns.filter((c) => c !== "patient_id").map((c) => (
                      <td key={c}>{String(r[c] ?? "")}</td>
                    ))}
                  </tr>
                ))}
              </>
            )}
          />
        )}
        {result && (
          <div className="pane output-pane" data-testid="output-cql">
            <header className="pane-header">
              <h3>Output</h3>
            </header>
            <PaginatedTable
              testId="results-table"
              rowCount={result.rows.length}
              stats={
                <>
                  {result.rows.length} rows · {result.columns.length} columns
                  {result.evaluated_at
                    ? ` · ${new Date(result.evaluated_at).toLocaleString()}`
                    : ""}
                  {` · ${result.timing_ms.evaluate}ms`}
                </>
              }
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
                        const dcls = isPopulation
                          ? cellDiffClass(runDiff, pid, c)
                          : null;
                        return (
                          <td
                            key={c}
                            className={
                              isPopulation
                                ? `cell-evidence${dcls ? " " + dcls : ""}`
                                : dcls
                                  ? dcls
                                  : undefined
                            }
                            data-testid={
                              isPopulation ? `cell-${pid}-${c}` : undefined
                            }
                            title={
                              isPopulation
                                ? `why: ${pid} · ${c}${dcls ? " · changed" : ""}`
                                : undefined
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
        {!scratch && !result && diags.length === 0 && !error && (
          <p className="pane-hint" data-testid="console-empty">
            Run evaluates the whole library; select an expression and Run
            selection evaluates just that, in context.
          </p>
        )}
      </div>

      <div
        className="tab-panel"
        hidden={activeTab !== "sql"}
        data-testid="console-panel-sql"
      >
        {result?.sql ? (
          <div className="sql-viewer" data-testid="sql-viewer">
            <pre className="sql-pre">{result.sql}</pre>
          </div>
        ) : (
          <p className="pane-hint" data-testid="sql-empty">
            Run an evaluation to see its translation SQL.
          </p>
        )}
      </div>

      <div
        className="tab-panel"
        hidden={activeTab !== "ast"}
        data-testid="console-panel-ast"
      >
        <div className="pane output-pane" data-testid="ast-pane">
          <header className="pane-header">
            <h3>AST</h3>
          </header>
          <AstTree cqlText={main.text} />
        </div>
      </div>

      <div
        className="tab-panel"
        hidden={activeTab !== "diags"}
        data-testid="console-panel-diags"
      >
        {evalDiags && evalDiags.length > 0 ? (
          <ul className="diag-list" data-testid="eval-diags">
            {evalDiags.map((d, i) => (
              <li key={i} className="diag-row">
                <span className="diag-code">{d.code}</span> {d.message}
              </li>
            ))}
          </ul>
        ) : (
          <p className="pane-hint" data-testid="eval-diags-empty">
            No evaluation diagnostics.
          </p>
        )}
      </div>
    </section>
  );
}

function renderValue(v: unknown): string {
  if (v === null || v === undefined) return "—";
  if (typeof v === "boolean") return v ? "true" : "false";
  if (typeof v === "object") return JSON.stringify(v);
  return String(v);
}
