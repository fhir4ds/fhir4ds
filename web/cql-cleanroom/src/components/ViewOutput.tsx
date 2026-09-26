import type { FlattenViewResult } from "../lib/protocol";
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
}: {
  viewResult: FlattenViewResult | null;
  runDiff: ReturnType<typeof diffRuns>;
}) {
  if (!viewResult?.ok || viewResult.columns.length === 0) {
    return (
      <p className="pane-hint" data-testid="view-output-empty">
        No view output yet — configure the ViewDefinition and let it
        flatten the saved MeasureReports.
      </p>
    );
  }
  return (
    <div className="pane output-pane" data-testid="output-view">
      <header className="pane-header">
        <h3>Output</h3>
      </header>
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
