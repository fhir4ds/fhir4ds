import { useEffect, useRef, useState } from "react";
import { workerRequest } from "./BootOverlay";
import { PaginatedTable } from "./PaginatedTable";
import { DiagnosticsRow } from "./EditorPane";
import { EvidencePopover } from "./EvidencePopover";
import { AstTree } from "./AstPane";
import { cellDiffClass, diffSummary } from "../lib/runDiff";
import { DefinesMatrix } from "./DefinesMatrix";
import { renderValue } from "../lib/formatValue";
import { useRunDiff } from "./MeasureReportOutput";
import type { CompareResult } from "../lib/verifyCompare";
import type {
  Diagnostics,
  LibraryText,
  DatasetSpec,
  EvaluateResult,
  EvidenceResult,
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
  | "defines"
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
    { id: "defines", label: "Defines" },
    { id: "cql", label: "CQL" },
    { id: "sql", label: "SQL" },
    { id: "ast", label: "AST" },
  ],
  measure: [
    { id: "mr", label: "Measure Report" },
    { id: "funnel", label: "Funnel" },
    { id: "defines", label: "Defines" },
  ],
  view: [{ id: "view", label: "View Output" }],
  // 6h: the Expected Results editor's console context — authored
  // expectations derived against the latest library run (#62).
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
  verifyCompare,
  compareStale,
  runRequest,
  runs,
  displayRun,
  onSelectRun,
  onManualRun,
  activeTab,
  onTabChange,
  recalcSeconds,
}: {
  libraries: LibraryText[];
  main: LibraryText;
  dataset: DatasetSpec | null;
  parameters: Record<string, unknown>;
  outputColumns: Record<string, string> | null;
  /** 6g: settings recalc delay — also debounces the Defines matrix. */
  recalcSeconds: number;
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
  /** 6h #62: derived expected-vs-actual compare (tests context). */
  verifyCompare: CompareResult | null;
  /** True when the latest library run failed — nothing to compare. */
  compareStale: boolean;
  /** REORG 6e: Ctrl/Cmd+Enter from the editor lands here (nonce bumps). */
  runRequest: { mode: "library" | "selection"; nonce: number } | null;
  /** REORG 6g: the run ring (last 20) + which entry the tabs render. */
  runs: RunEntry[];
  displayRun: RunEntry | null;
  onSelectRun: (id: string | null) => void;
  /** Manual runs (Run button / Ctrl+Enter) land in App's ring. */
  onManualRun: (p: {
    mode: "library" | "selection";
    library: string;
    cql: string;
    ok: boolean;
    sql?: string;
    rows?: Array<Record<string, unknown>>;
    columns?: string[];
    column_types?: Record<string, string>;
    ms?: number | null;
    diags?: Diagnostics[];
  }) => void;
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
        library: main.name,
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
                {r.payload?.library ? ` · ${r.payload.library}` : ""}
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
        hidden={activeTab !== "defines"}
        data-testid="console-panel-defines"
      >
        <DefinesMatrix
          libraries={libraries}
          main={main}
          dataset={dataset}
          parameters={parameters}
          visible={activeTab === "defines"}
          debounceMs={recalcSeconds > 0 ? recalcSeconds * 1000 : 1000}
        />
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
        className="tab-panel compare-panel"
        hidden={activeTab !== "compare"}
        data-testid="console-panel-compare"
      >
        {context === "tests" ? (
          <CompareOutput result={verifyCompare} stale={compareStale} />
        ) : null}
      </div>
    </section>
  );
}

/**
 * 6h #62: expected-vs-actual matrix, derived client-side (see
 * lib/verifyCompare.ts) — one row per expected patient, one column per
 * population; mismatches sort first and render red. The N/M passed chip
 * rides the pager row's right end (the `.editor-stat` bottom-right
 * convention) and click-filters to failing rows. Recalcs automatically
 * with every heartbeat run — no button.
 */
function CompareOutput({
  result,
  stale,
}: {
  result: CompareResult | null;
  stale: boolean;
}) {
  const [onlyFailed, setOnlyFailed] = useState(false);
  if (stale) {
    return (
      <p className="pane-hint" data-testid="compare-empty">
        The latest library run failed — fix the diagnostics and the
        compare refreshes automatically.
      </p>
    );
  }
  if (!result || result.rows.length === 0) {
    return (
      <p className="pane-hint" data-testid="compare-empty">
        Author expected values in the Expected Results editor — the
        compare recalculates automatically on every run.
      </p>
    );
  }
  const shown = onlyFailed
    ? result.rows.filter((r) => r.mismatch)
    : result.rows;
  const allPass = result.passed === result.total;
  return (
    <PaginatedTable
      testId="compare-table"
      rowCount={shown.length}
      stats={
        <button
          className={`tests-summary ${allPass ? "pass" : "fail"}`}
          data-testid="tests-summary"
          title="show only failing rows"
          onClick={() => setOnlyFailed((v) => !v)}
        >
          {result.passed}/{result.total} passed
          {onlyFailed ? " · failing only" : ""}
        </button>
      }
      header={
        <tr>
          <th>patient_id</th>
          {result.rows[0]?.cells.map((c) => (
            <th key={c.code}>{c.code}</th>
          ))}
        </tr>
      }
      renderRows={({ slice }) =>
        slice(shown).map((r) => (
          <tr key={r.pid} data-testid={`compare-row-${r.pid}`}>
            <td>
              {r.pid}
              {r.missing && (
                <span className="type-badge" title="no row in the actual run">
                  no data
                </span>
              )}
            </td>
            {r.cells.map((c) => (
              <td
                key={c.code}
                className={c.match ? "compare-cell-match" : "compare-cell-miss"}
                data-testid={`compare-${r.pid}-${c.code}`}
              >
                {c.match
                  ? renderValue(c.expected)
                  : `exp ${renderValue(c.expected)} · got ${c.actual === null ? "—" : renderValue(c.actual)}`}
              </td>
            ))}
          </tr>
        ))
      }
    />
  );
}
