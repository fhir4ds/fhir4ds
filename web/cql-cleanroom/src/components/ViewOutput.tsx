import type { FlattenViewResult } from "../lib/protocol";
import { Spinner } from "./Spinner";
import { PaginatedTable } from "./PaginatedTable";
import { cellDiffClass, diffPopKey, diffRuns } from "../lib/runDiff";

/**
 * REORG phase 6b: the View Definition OUTPUT — flatten table over the
 * stored viewDefs — rendered inside the CQL console's "view" panel
 * while a view editor tab is active (the col2 stacked pane is gone).
 */
export function ViewOutputPanel({
  viewResult,
  runDiff,
  busy = false,
}: {
  viewResult: FlattenViewResult | null;
  runDiff: ReturnType<typeof diffRuns>;
  /** S32: a flatten is in flight — show the shared spinner instead of
   *  the empty-state text (no loading-text flash). */
  busy?: boolean;
}) {
  if (busy && (!viewResult || !viewResult.ok)) {
    return (
      <p className="pane-hint" data-testid="view-output-loading">
        <Spinner label="flattening view" />
      </p>
    );
  }
  if (viewResult && !viewResult.ok) {
    // Real flatten failure: surface the diagnostics (never a silent
    // empty state that looks like "not configured").
    return (
      <p className="pane-hint" data-testid="view-output-error">
        {viewResult.diagnostics?.map((d) => d.message).join("; ") ||
          "view flatten failed"}
      </p>
    );
  }
  if (!viewResult || viewResult.columns.length === 0) {
    // PENDING/idle is still work-in-progress territory: the console
    // shows the shared spinner, never static hint text (Joel doctrine,
    // repeated): "the flatten is pending" is indistinguishable from
    // "not configured yet" to the user — a spinner communicates both.
    return (
      <p className="pane-hint" data-testid="view-output-empty">
        <Spinner label="flattening view" />
      </p>
    );
  }
  return (
    <div data-testid="output-view">
      <PaginatedTable
        testId="view-table"
        rowCount={viewResult.rows.length}
        stats={`${viewResult.rows.length} rows · ${viewResult.columns.length} columns`}
        header={
          <tr>
            {viewResult.columns.map((c) => (
              <th key={c}>{c}</th>
            ))}
          </tr>
        }
        renderRows={({ slice }) =>
          slice(viewResult.rows).map((r, i) => {
            const pid = String(r.patient_id ?? r.subject ?? "");
            const barePid = pid.replace(/^Patient\//, "");
            return (
              <tr key={i}>
                {viewResult.columns.map((c) => {
                  const dcls =
                    c === "patient_id" || c === "subject"
                      ? null
                      : cellDiffClass(runDiff, barePid, diffPopKey(c));
                  return (
                    <td key={c} className={dcls ?? undefined}>
                      {r[c] === null || r[c] === undefined
                        ? "—"
                        : String(r[c])}
                    </td>
                  );
                })}
              </tr>
            );
          })
        }
      />
    </div>
  );
}
