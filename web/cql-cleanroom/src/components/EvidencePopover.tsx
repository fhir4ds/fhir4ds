import type { EvidenceResult } from "../lib/protocol";

/**
 * Cell-level evidence popover (E2): rendered under the results table
 * when a population cell is clicked. Shows the clicked (patient,
 * population) pair's evidence from explain_patient — target resources,
 * operator, threshold, and the clause trace — using the shared tree
 * row styling.
 */
export function EvidencePopover({
  evidence,
  patientId,
  population,
  onClose,
}: {
  evidence: EvidenceResult | null;
  patientId: string;
  population: string;
  onClose: () => void;
}) {

  // Filter to the clicked define; fall back to all when the column
  // name does not match (aliased output columns).
  const relevant = (evidence?.definitions ?? []).filter(
    (d) => d.column === population,
  );
  const defs = relevant.length ? relevant : (evidence?.definitions ?? []);
  const popValue = evidence?.populations?.[population];

  return (
    <div className="pane output-pane evidence-popover" data-testid="evidence-popover">
      <header className="pane-header">
        <h3>
          Evidence · {patientId} · {population}
          {popValue === true || popValue === false ? (
            <span
              className={`evidence-verdict ${popValue ? "true" : "false"}`}
              data-testid="evidence-verdict"
            >
              {String(popValue)}
            </span>
          ) : null}
        </h3>
        <div className="pane-actions">
          <button data-testid="evidence-popover-close" onClick={onClose}>
            ×
          </button>
        </div>
      </header>
      {!evidence && (
        <p className="pane-hint" data-testid="evidence-loading">
          explaining…
        </p>
      )}
      {evidence && !evidence.ok && (
        <div className="diag-list" data-testid="evidence-popover-error">
          {(evidence.diagnostics ?? []).map((d, i) => (
            <div key={i} className="diag-row diag-error">
              {d.message}
            </div>
          ))}
        </div>
      )}
      {evidence?.ok && defs.length === 0 && (
        <p className="pane-hint">no evidence recorded for this population</p>
      )}
      {evidence?.ok &&
        defs.map((d) => (
          <div key={d.column} className="evidence-def">
            <div className="evidence-def-head">
              <span className="builder-caret-placeholder" aria-hidden="true" />
              <span className="dataset-type-name">{d.column}</span>
              <span
                className={`evidence-verdict ${d.result ? "true" : "false"}`}
              >
                {d.result === null ? "null" : String(d.result)}
              </span>
            </div>
            {d.evidence.length === 0 && (
              <div className="evidence-row">
                <span className="builder-caret-placeholder" aria-hidden="true" />
                <span className="ast-key">no contributing resources</span>
              </div>
            )}
            {d.evidence.map((ev, i) => {
              const e = ev as {
                target?: string;
                attribute?: string | null;
                value?: unknown;
                operator?: string;
                threshold?: string;
                trace?: string[];
              };
              return (
                <div
                  key={i}
                  className="evidence-row"
                  data-testid={`evidence-row-${i}`}
                >
                  <span className="builder-caret-placeholder" aria-hidden="true" />
                  <span className="ast-key">{e.target ?? "—"}</span>
                  <span className="ast-value">
                    {e.operator ?? ""}
                    {e.threshold ? ` ${e.threshold}` : ""}
                    {e.attribute ? ` · ${e.attribute}` : ""}
                    {e.value !== null && e.value !== undefined
                      ? ` = ${String(e.value)}`
                      : ""}
                  </span>
                </div>
              );
            })}
          </div>
        ))}
    </div>
  );
}
