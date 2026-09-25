import { useState } from "react";
import { workerRequest } from "./BootOverlay";
import type { CompareEvidenceResult } from "../lib/protocol";
import type { RunEntry } from "../state/workspace";
import { driftKind, formatRunTimestamp } from "../lib/runHistory";

/**
 * RunCompare (U2): prior-run comparison only. The per-patient explain
 * drill-in moved to the results-table cell popover (EvidencePopover);
 * this pane lives in the Evidence drawer for baseline regression
 * checks: select a prior run → compare_evidence against the current
 * rows, with SHA-256 drift warnings and rename/delete management.
 */
export function RunCompare({
  runHistory,
  currentArtifact,
  currentLibraryHash,
  currentDatasetHash,
  onDeleteRun,
  onRenameRun,
}: {
  runHistory: RunEntry[];
  /** Row-shaped memberships of the latest evaluation (compare target). */
  currentArtifact: Record<string, unknown> | null;
  currentLibraryHash: string | null;
  currentDatasetHash: string | null;
  onDeleteRun: (id: string) => void;
  onRenameRun: (id: string, name: string) => void;
}) {
  const [selectedRun, setSelectedRun] = useState("");
  const [delta, setDelta] = useState<CompareEvidenceResult | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [running, setRunning] = useState(false);

  const selected = runHistory.find((r) => r.id === selectedRun) ?? null;

  const runCompare = async () => {
    setErr(null);
    setDelta(null);
    if (!currentArtifact) {
      setErr("run an evaluation first — the latest result is the compare target");
      return;
    }
    if (!selected) {
      setErr("select a prior run to compare against");
      return;
    }
    setRunning(true);
    try {
      const resp = await workerRequest({
        type: "compare_evidence",
        baseline: selected.artifact,
        current: currentArtifact,
      });
      const parsed: CompareEvidenceResult = JSON.parse(resp.envelope);
      setDelta(parsed);
    } catch (e) {
      setErr(String(e));
    } finally {
      setRunning(false);
    }
  };

  const drift = selected
    ? driftKind(selected, currentLibraryHash ?? "", currentDatasetHash ?? "")
    : null;

  return (
    <div className="run-compare" data-testid="ev-compare">
      <h3>
        Compare against prior run{" "}
        <span className="ev-run-count">
          ({runHistory.length}/20 runs)
        </span>
      </h3>
      {runHistory.length === 0 ? (
        <p className="pane-hint" data-testid="compare-no-runs">
          No saved runs yet — each evaluation saves one automatically.
        </p>
      ) : (
        <>
          <div className="ev-run-controls">
            <select
              data-testid="compare-select"
              value={selectedRun}
              onChange={(e) => {
                setSelectedRun(e.target.value);
                setDelta(null);
              }}
              aria-label="prior run"
            >
              <option value="">— select run —</option>
              {runHistory
                .slice()
                .reverse()
                .map((r) => (
                  <option key={r.id} value={r.id}>
                    {r.name !== formatRunTimestamp(r.createdAt)
                      ? `${r.name} · ${formatRunTimestamp(r.createdAt)}`
                      : r.name}
                  </option>
                ))}
            </select>
            <button
              data-testid="compare-run"
              onClick={runCompare}
              disabled={running || !selectedRun || !currentArtifact}
            >
              Compare
            </button>
            {selected && (
              <button
                className="link-btn"
                data-testid="run-rename"
                onClick={() => {
                  const name = prompt("run name", selected.name);
                  if (name && name.trim()) onRenameRun(selected.id, name.trim());
                }}
              >
                rename
              </button>
            )}
            {selected && (
              <button
                className="link-btn"
                data-testid="run-delete"
                onClick={() => {
                  onDeleteRun(selected.id);
                  setSelectedRun("");
                  setDelta(null);
                }}
              >
                delete
              </button>
            )}
          </div>
          {drift && (drift.library || drift.dataset) && (
            <div className="drift-warning" data-testid="compare-drift">
              ⚠ {drift.library ? "library" : ""}
              {drift.library && drift.dataset ? " + " : ""}
              {drift.dataset ? "dataset" : ""} changed since this run —
              differences may be data, not logic.
            </div>
          )}
        </>
      )}
      {err && <div className="ev-error" data-testid="evidence-error">{err}</div>}
      {delta && (
        <div className="ev-delta" data-testid="compare-delta">
          {(delta.patients ?? []).length > 0 ? (
            <table className="results-table delta-table">
              <thead>
                <tr>
                  <th>patient</th>
                  <th>column</th>
                  <th>classification</th>
                  <th>from</th>
                  <th>to</th>
                </tr>
              </thead>
              <tbody>
                {(delta.patients ?? []).map((row, i) => (
                  <tr key={i} data-testid="compare-row">
                    <td>{row.patient_id}</td>
                    <td>{row.column}</td>
                    <td>
                      <span className={`badge delta-class-${row.classification}`}>
                        {row.classification}
                      </span>
                    </td>
                    <td>{row.from === null ? "—" : String(row.from)}</td>
                    <td>{row.to === null ? "—" : String(row.to)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <p className="pane-hint" data-testid="compare-identical">
              identical — no population differences vs the selected run
            </p>
          )}
        </div>
      )}
    </div>
  );
}
