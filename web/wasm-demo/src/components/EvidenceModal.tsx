import { useEffect, useCallback } from "react";
import type { AuditCell, EvidenceGroup } from "../lib/narrative";
import { generateNarrative } from "../lib/narrative";

interface EvidenceModalProps {
  cell: AuditCell;
  columnName: string;
  onClose: () => void;
}

export function EvidenceModal({ cell, columnName, onClose }: EvidenceModalProps) {
  const narrative = generateNarrative(columnName, cell.evidence ?? [], cell.result);
  const evidence = cell.evidence ?? [];

  const handleKeyDown = useCallback(
    (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    },
    [onClose],
  );

  useEffect(() => {
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [handleKeyDown]);

  return (
    <div className="evidence-backdrop" onClick={onClose}>
      <div className="evidence-modal" onClick={(e) => e.stopPropagation()}>
        <div className="evidence-header">
          <h3>{columnName}</h3>
          <span className={`cell-bool ${cell.result ? "cell-bool--true" : "cell-bool--false"}`}>
            {cell.result ? "✓ true" : "✗ false"}
          </span>
          <button className="evidence-close" onClick={onClose}>✕</button>
        </div>

        {/* Narration */}
        <section className="evidence-section">
          <h4>Narrative</h4>
          <div className="evidence-narrative">
            {narrative.map((line, i) => (
              <p key={i}>{line}</p>
            ))}
          </div>
        </section>

        {/* Logic Trace */}
        {evidence.length > 0 && evidence.some((e) => e.trace?.length) && (
          <section className="evidence-section">
            <h4>Logic Trace</h4>
            <div className="evidence-trace">
              {evidence
                .filter((e) => e.trace?.length)
                .map((e, i) => (
                  <div key={i} className="trace-breadcrumbs">
                    {(e.trace ?? []).map((step, j) => (
                      <span key={j}>
                        {j > 0 && <span className="trace-arrow"> → </span>}
                        <span className="trace-step">{step}</span>
                      </span>
                    ))}
                  </div>
                ))}
            </div>
          </section>
        )}

        {/* Evidence Table */}
        {evidence.length > 0 && (
          <section className="evidence-section">
            <h4>Evidence Details</h4>
            <div className="table-wrapper">
              <table className="results-table evidence-table">
                <thead>
                  <tr>
                    <th>Attribute</th>
                    <th>Operator</th>
                    <th>Threshold</th>
                    <th>Findings</th>
                  </tr>
                </thead>
                <tbody>
                  {evidence.map((group, i) => (
                    <EvidenceRow key={i} group={group} />
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        )}
      </div>
    </div>
  );
}

function EvidenceRow({ group }: { group: EvidenceGroup }) {
  const findings = group.findings ?? [];
  return (
    <tr>
      <td>{group.attribute ?? "—"}</td>
      <td>{group.operator ?? "—"}</td>
      <td>{group.threshold ?? "—"}</td>
      <td>
        {findings.length === 0 ? (
          "—"
        ) : (
          <span title={findings.map((f) => `${f.target}: ${f.value ?? "—"}`).join("\n")}>
            {findings[0].target ?? "Resource"}
            {findings[0].value && ` = ${findings[0].value}`}
            {findings.length > 1 && ` (+${findings.length - 1} more)`}
          </span>
        )}
      </td>
    </tr>
  );
}
