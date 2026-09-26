import type { EvaluateResult, FlattenViewResult } from "../lib/protocol";
import { PaginatedTable } from "./PaginatedTable";
import { cellDiffClass, diffPopKey } from "../lib/runDiff";
import { useRunDiff } from "./MeasureReportOutput";

/**
 * WORKBENCH_REORG phase 5: the col2 View Definition pane — flatten
 * output of the stored viewDefs on top, the ViewPane config below.
 */
export function ViewOutputPane({
  result,
  viewResult,
  baselineArtifact,
  viewSlot,
  open,
  onToggle,
}: {
  result: EvaluateResult | null;
  viewResult: FlattenViewResult | null;
  baselineArtifact: import("../lib/runDiff").Artifact | null;
  viewSlot: React.ReactNode;
  open: boolean;
  onToggle: () => void;
}) {
  const runDiff = useRunDiff(result, baselineArtifact);
  return (
    <section className="pane" data-testid="pane-view">
      <header className="pane-header">
        <h2>View Definition</h2>
        <div className="pane-actions">
          <button
            className="pane-action"
            data-testid="pane-toggle-view"
            onClick={onToggle}
            title="Show or hide this pane"
          >
            {open ? "▾" : "▸"}
          </button>
        </div>
      </header>
      <div className="pane-body" data-testid="pane-view-body" hidden={!open}>
      {viewResult?.ok && viewResult.columns.length > 0 && (
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
                        <td key="x" className={dcls ?? undefined}>
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
      )}
      {viewSlot}
      </div>
    </section>
  );
}
