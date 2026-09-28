import { useEffect, useRef, useState } from "react";
import { workerRequest } from "./BootOverlay";
import { PaginatedTable } from "./PaginatedTable";
import { DiagnosticsRow } from "./EditorPane";
import { EvidencePopover } from "./EvidencePopover";
import { AstTree } from "./AstPane";
import { cellDiffClass, diffSummary } from "../lib/runDiff";
import { useRunDiff } from "./MeasureReportOutput";
import type {
  Diagnostics,
  LibraryText,
  DatasetSpec,
  EvaluateResult,
  EvidenceResult,
  VerifyEnvelope,
} from "../lib/protocol";
import type { Artifact } from "../lib/runDiff";
import type { RunEntry } from "../state/workspace";
import { formatRunTimestamp } from "../lib/runHistory";

/**
 * REORG phase 6b — the console, now the single home for run OUTPUT.
 * Its sub-tab set is keyed on the ACTIVE editor tab's kind:
 *   library (or kinds without output) → Results / SQL / AST / CQL / Diags
 *   measure → Measure Report (pivot) + Funnel (attrition Sankey)
 *   view    → the ViewDefinition flatten output
 * REORG 6g — the console is RUN-CENTRIC: every tab renders from the
 * selected run's replay payload (the run switcher sits right of the
 * tabs). Runs are triggered from the LIBRARY EDITOR (Run button /
 * Ctrl+Enter); the console only displays. The console docks bottom
 * (col1, under the editor) or right (col2).
 *
 * A failing evaluation AUTO-SWITCHES the console to Diagnostics (and
 * back to Results once a run succeeds again) in library contexts.
 */

export type ConsoleTab =
  | "results"
  | "sql"
  | "ast"
  | "cql"
  | "mr"
  | "funnel"
  | "view"
  | "compare";
export type ConsoleContext = "library" | "measure" | "view" | "tests";
export type ConsolePlacement = "bottom" | "right";

const CONTEXT_TABS: Record<ConsoleContext, Array<{ id: ConsoleTab; label: string }>> = {
  library: [
    { id: "results", label: "Results" },
    { id: "cql", label: "CQL" },
    { id: "sql", label: "SQL" },
    { id: "ast", label: "AST" },
  ],
  measure: [
    { id: "mr", label: "Measure Report" },
    { id: "funnel", label: "Funnel" },
  ],
  view: [{ id: "view", label: "View Output" }],
  // 6h: the Expected Results editor's console context — the authored
  // expected values vs the actual run, compared by the Run tests action.
  tests: [{ id: "compare", label: "Compare" }],
};

export function ResultsConsole({
  libraries,
  main,
  dataset,
  parameters,
  outputColumns,
  selection,
  result,
  baselineArtifact,
  context,
  mrOutput,
  funnelOutput,
  viewOutput,
  verifyResult,
  runRequest,
  runs,
  displayRun,
  onSelectRun,
  onManualRun,
  onCaptureExpected,
  canCaptureExpected,
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
  baselineArtifact: Artifact | null;
  /** Active editor kind — decides which sub-tabs exist. */
  context: ConsoleContext;
  /** Measure Report pivot node (measure context). */
  mrOutput: React.ReactNode;
  /** REORG 6e: attrition-funnel node (measure context). */
  funnelOutput: React.ReactNode;
  /** View flatten output node (view context). */
  viewOutput: React.ReactNode;
  /** 6h: expected-vs-actual verify envelope (tests context). */
  verifyResult: VerifyEnvelope | null;
  /** REORG 6e: Ctrl/Cmd+Enter from the editor lands here (nonce bumps). */
  runRequest: { mode: "library" | "selection"; nonce: number } | null;
  /** REORG 6g: the run ring (last 20) + which entry the tabs render. */
  runs: RunEntry[];
  displayRun: RunEntry | null;
  onSelectRun: (id: string | null) => void;
  /** Manual runs (Run button / Ctrl+Enter) land in App's ring. */
  onManualRun: (p: {
    mode: "library" | "selection";
    cql: string;
    ok: boolean;
    sql?: string;
    rows?: Array<Record<string, unknown>>;
    columns?: string[];
    column_types?: Record<string, string>;
    ms?: number | null;
    diags?: Diagnostics[];
  }) => void;
  /** 6f: capture the current run's populations as the active measure's
   *  expected reports (Measure Report tab header). */
  onCaptureExpected?: () => void;
  canCaptureExpected?: boolean;
  activeTab: ConsoleTab;
  onTabChange: (t: ConsoleTab) => void;
}) {
  const [error, setError] = useState<string | null>(null);
  const seqRef = useRef(0);

  // Errors are not a tab: every failed run carries its diagnostics in
  // the run payload, and the Results panel renders them inline — the
  // failure stays next to the output it replaced (no tab switching).

  // A context switch can strand the persisted tab (e.g. "sql" while a
  // view editor is active) — clamp to the context's first tab.
  const tabs = CONTEXT_TABS[context];
  useEffect(() => {
    if (!tabs.some((t) => t.id === activeTab)) {
      onTabChange(tabs[0].id);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [context, activeTab]);

  // Ctrl/Cmd+Enter in the editor: (re)run via the request nonce.
  const runRef = useRef<typeof run>(null!);
  useEffect(() => {
    if (runRequest) void runRef.current(runRequest.mode);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [runRequest?.nonce]);
  const run = async (mode: "library" | "selection") => {
    const seq = ++seqRef.current;
    setError(null);
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
              emit_sql: true,
            },
      );
      if (seq !== seqRef.current) return;
      const env = JSON.parse((resp as { envelope: string }).envelope) as {
        ok: boolean;
        cql?: string;
        sql?: string;
        diagnostics?: Diagnostics[];
        columns?: string[];
        column_types?: Record<string, string>;
        rows?: Array<Record<string, unknown>>;
        timing_ms?: Record<string, number>;
      };
      // REORG 6g: the response becomes a RING ENTRY — the switcher can
      // replay its table, SQL, AST and executed CQL later. App owns the
      // history write; the new entry overrides the displayed result.
      onManualRun({
        mode,
        cql: env.cql ?? main.text,
        ok: !!env.ok,
        sql: env.ok ? env.sql : undefined,
        rows: env.rows,
        columns: env.columns,
        column_types: env.column_types,
        ms: env.timing_ms?.evaluate ?? null,
        diags: env.ok ? undefined : env.diagnostics ?? [],
      });
    } catch (e) {
      if (seq === seqRef.current) {
        setError(e instanceof Error ? e.message : String(e));
      }
    }
  };
  runRef.current = run;

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

  // Diff chips + per-cell diff classes describe the LATEST run; a
  // pinned historical run renders plain (its diff window has moved on).
  const latestRun = runs[runs.length - 1] ?? null;
  const isLatest = displayRun != null && displayRun.id === latestRun?.id;
  const payload = displayRun?.payload ?? null;
  const payloadRows = payload?.rows;
  const payloadColumns = payload?.columns;
  const runDiff = useRunDiff(result, baselineArtifact);
  const dsum = diffSummary(runDiff);

  return (
    <section className="pane results-console" data-testid="results-console">
      <div className="tab-strip console-subtabs" data-testid="console-subtabs">
        {tabs.map((t) => (
          <button
            key={t.id}
            className={`tab ${activeTab === t.id ? "active" : ""}`}
            data-testid={`console-tab-${t.id}`}
            onClick={() => onTabChange(t.id)}
          >
            {t.label}
          </button>
        ))}
        <div className="console-toolbar-right">
          {isLatest && runDiff && (dsum.changed || dsum.added || dsum.removed) ? (
            <span className="diff-chips" data-testid="diff-chips">
              <span className="diff-chip up" data-testid="diff-chip-changed">
                {dsum.changed} changed
              </span>
              {dsum.added > 0 && (
                <span className="diff-chip add" data-testid="diff-chip-added">
                  {dsum.added} added
                </span>
              )}
              {dsum.removed > 0 && (
                <span
                  className="diff-chip rem"
                  data-testid="diff-chip-removed"
                  title={runDiff.removedPatients.join(", ")}
                >
                  {dsum.removed} removed
                </span>
              )}
            </span>
          ) : null}
          {activeTab === "mr" && context === "measure" && onCaptureExpected && (
            <button
              className="pane-action"
              data-testid="capture-expected"
              disabled={!canCaptureExpected}
              title="Save the current run's populations as this measure's expected results"
              onClick={onCaptureExpected}
            >
              Capture as expected
            </button>
          )}
          <select
            className="console-run-select"
            data-testid="console-run-select"
            title="replay one of the last 20 runs"
            value={isLatest ? "" : (displayRun?.id ?? "")}
            onChange={(e) =>
              onSelectRun(e.target.value === "" ? null : e.target.value)
            }
          >
            <option value="">latest</option>
            {[...runs].reverse().map((r) => (
              <option key={r.id} value={r.id}>
                {formatRunTimestamp(r.createdAt)} · {r.payload?.mode ?? "library"}
                {r.payload?.diags?.length ? " · error" : ""}
              </option>
            ))}
          </select>
        </div>
      </div>

      <div
        className="tab-panel"
        hidden={activeTab !== "results"}
        data-testid="console-panel-results"
      >
        {error && <p className="pane-error" data-testid="console-error">{error}</p>}
        {payload?.diags && payload.diags.length > 0 && (
          <div className="diag-list" data-testid="console-diags">
            {payload.diags.map((d, i) => (
              <DiagnosticsRow key={i} diag={d} />
            ))}
          </div>
        )}
        {payloadRows && payloadColumns && payloadColumns.length > 0 && (
          <PaginatedTable
            testId="results-table"
            rowCount={payloadRows.length}
            stats={
              <>
                {payloadRows.length} rows · {payloadColumns.length} columns
                {displayRun
                  ? ` · ${formatRunTimestamp(displayRun.createdAt)}`
                  : ""}
                {payload?.ms != null ? ` · ${Math.round(payload.ms)}ms` : ""}
              </>
            }
            header={
              <tr>
                {payloadColumns.map((c) => (
                  <th key={c}>
                    {c}
                    {payload?.column_types?.[c] && (
                      <span
                        className="type-badge"
                        data-testid={`type-badge-${c}`}
                        title="CQL type"
                      >
                        {payload.column_types[c]}
                      </span>
                    )}
                  </th>
                ))}
              </tr>
            }
            renderRows={({ slice }) =>
              slice(payloadRows).map((row) => {
                const pid = String(row.patient_id ?? "");
                return (
                  <tr key={pid}>
                    {payloadColumns.map((c) => {
                      const isPopulation =
                        c !== "patient_id" && row[c] !== undefined;
                      const dcls =
                        isLatest && isPopulation
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
        )}
        {!payload && (
          <p className="pane-hint" data-testid="console-empty">
            Run from the editor toolbar (or Ctrl/Cmd+Enter): the whole
            library runs, a selection runs just that expression. The last
            20 runs stay switchable above.
          </p>
        )}
        {cellEvidence && (
          <EvidencePopover
            evidence={cellEvidence.evidence}
            patientId={cellEvidence.patientId}
            population={cellEvidence.population}
            onClose={() => setCellEvidence(null)}
          />
        )}
      </div>

      <div
        className="tab-panel"
        hidden={activeTab !== "sql"}
        data-testid="console-panel-sql"
      >
        {payload?.sql ? (
          <div className="sql-viewer" data-testid="sql-viewer">
            <pre className="sql-pre">{payload.sql}</pre>
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
        {payload?.cql ? (
          <AstTree cqlText={payload.cql} />
        ) : (
          <p className="pane-hint" data-testid="ast-empty">
            Run an evaluation to see its AST.
          </p>
        )}
      </div>

      <div
        className="tab-panel"
        hidden={activeTab !== "cql"}
        data-testid="console-panel-cql"
      >
        {payload?.cql ? (
          <div className="sql-viewer" data-testid="cql-viewer">
            <pre className="sql-pre">{payload.cql}</pre>
          </div>
        ) : (
          <p className="pane-hint" data-testid="cql-empty">
            Run an evaluation to see the exact CQL that executed.
          </p>
        )}
      </div>

      <div
        className="tab-panel"
        hidden={activeTab !== "mr"}
        data-testid="console-panel-mr"
      >
        {context === "measure" ? mrOutput : null}
      </div>

      <div
        className="tab-panel"
        hidden={activeTab !== "funnel"}
        data-testid="console-panel-funnel"
      >
        {context === "measure" ? funnelOutput : null}
      </div>

      <div
        className="tab-panel"
        hidden={activeTab !== "view"}
        data-testid="console-panel-view"
      >
        {context === "view" ? viewOutput : null}
      </div>

      <div
        className="tab-panel"
        hidden={activeTab !== "compare"}
        data-testid="console-panel-compare"
      >
        {context === "tests" ? <CompareOutput result={verifyResult} /> : null}
      </div>
    </section>
  );
}

/** 6h: expected-vs-actual summary — moved out of the TestsPane so the
 *  comparison lands in the console like every other run output. */
function CompareOutput({ result }: { result: VerifyEnvelope | null }) {
  if (!result) {
    return (
      <p className="pane-hint" data-testid="compare-empty">
        Press Run tests in the Expected Results editor to compare the
        authored expectations against the actual evaluation.
      </p>
    );
  }
  return (
    <div className="tests-summary" data-testid="tests-summary">
      <span className={result.passed ? "pass" : "fail"}>
        {result.tests.passed}/{result.tests.total} passed
      </span>
      {result.tests.failures.length > 0 && (
        <div className="failures-wrap">
          <table className="failures-table" data-testid="failures-table">
            <thead>
              <tr>
                <th>Patient</th>
                <th>Target</th>
                <th>Expected</th>
                <th>Actual</th>
                <th>Reason</th>
              </tr>
            </thead>
            <tbody>
              {result.tests.failures.map((f, i) => (
                <tr key={i}>
                  <td>{f.patient}</td>
                  <td>{f.target}</td>
                  <td>{String(f.expected)}</td>
                  <td>{f.actual === null ? "—" : String(f.actual)}</td>
                  <td>{f.reason ?? ""}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function renderValue(v: unknown): string {
  if (v === null || v === undefined) return "—";
  if (typeof v === "boolean") return v ? "true" : "false";
  if (typeof v === "object") return JSON.stringify(v);
  return String(v);
}
