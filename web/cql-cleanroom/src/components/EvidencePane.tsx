import { useRef, useState } from "react";
import { workerRequest } from "./BootOverlay";
import type { CompareEvidenceResult } from "../lib/protocol";
import type { EvidenceResult, LibraryText } from "../lib/protocol";
import type { RunEntry } from "../state/workspace";
import { driftKind, formatRunTimestamp } from "../lib/runHistory";

/**
 * C1-U7 EvidencePane: explain_patient drill-in + population Sankey +
 * evidence.json import.
 *
 * - Explain: audit structs (patient pushdown) → populations badges +
 *   per-definition evidence rows (target/attribute/value/operator/
 *   threshold/trace).
 * - Sankey: evaluate_library population rows → IPP→… flow with
 *   per-transition counts (FHIR CQM attribution order).
 * - Import: evidence.json artifact (operations `explain --evidence`)
 *   rendered with the same views offline. Delta view is cycle 2.
 */

interface EvidenceItem {
  target: string | null;
  attribute: string | null;
  value: string | null;
  operator: string | null;
  threshold: string | null;
  trace: string[] | null;
}

interface DefinitionEvidence {
  column: string;
  result: boolean | null;
  evidence: EvidenceItem[];
}

function EvidenceRows({ items }: { items: EvidenceItem[] }) {
  if (!items.length) {
    return <div className="ev-empty">no evidence recorded</div>;
  }
  return (
    <ul className="ev-list" data-testid="ev-list">
      {items.map((ev, i) => (
        <li key={i} className="ev-item">
          <div className="ev-line">
            <span className="ev-target">{ev.target ?? "—"}</span>
            {ev.attribute && <span className="ev-attr">.{ev.attribute}</span>}
            {ev.operator && <span className="ev-op"> {ev.operator} </span>}
            {ev.threshold != null && (
              <span className="ev-threshold">{ev.threshold}</span>
            )}
            {ev.value != null && (
              <span className="ev-value"> → {ev.value}</span>
            )}
          </div>
          {ev.trace && ev.trace.length > 0 && (
            <div className="ev-trace">via {ev.trace.join(" → ")}</div>
          )}
        </li>
      ))}
    </ul>
  );
}

export function EvidencePane({
  libraries,
  main,
  dataset,
  outputColumns,
  runHistory,
  currentArtifact,
  currentLibraryHash,
  currentDatasetHash,
  onDeleteRun,
  onRenameRun,
}: {
  libraries: LibraryText[];
  main: LibraryText;
  dataset: { resources: unknown[] } | null;
  outputColumns: Record<string, string> | null;
  /** Local run history (WORKBENCH_REORG §3.3). */
  runHistory: RunEntry[];
  /** Row-shaped memberships of the latest evaluation (compare target). */
  currentArtifact: RunEntry["artifact"] | null;
  currentLibraryHash: string | null;
  currentDatasetHash: string | null;
  onDeleteRun: (id: string) => void;
  onRenameRun: (id: string, name: string) => void;
}) {
  const [patientId, setPatientId] = useState("p1");
  const [env, setEnv] = useState<EvidenceResult | null>(null);
  const [running, setRunning] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  // §3.3 Compare: selected prior run + delta envelope. The current
  // side is the latest evaluation artifact (not Explain output).
  const [selectedRun, setSelectedRun] = useState<string>("");
  const [delta, setDelta] = useState<CompareEvidenceResult | null>(null);
  const fileRef = useRef<HTMLInputElement | null>(null);

  const runExplain = async () => {
    if (!dataset) {
      setErr("load a dataset first");
      return;
    }
    setRunning(true);
    setErr(null);
    try {
      const resp = await workerRequest({
        type: "explain_patient",
        libraries,
        main,
        dataset,
        patient_id: patientId,
        output_columns: outputColumns,
      });
      const parsed: EvidenceResult = JSON.parse(resp.envelope);
      setEnv(parsed);
    } catch (e) {
      setErr(String(e));
    } finally {
      setRunning(false);
    }
  };

  const importEvidence = async (file: File) => {
    try {
      const text = await file.text();
      const parsed = JSON.parse(text);
      if (Array.isArray(parsed)) {
        setEnv({
          schema: 1,
          ok: true,
          patient_id: file.name,
          populations: {},
          definitions: parsed as unknown as DefinitionEvidence[],
        } as EvidenceResult);
      } else if (parsed.definitions || parsed.populations) {
        setEnv(parsed as EvidenceResult);
      } else {
        setErr("not an evidence artifact: no definitions/populations");
      }
    } catch (e) {
      setErr(`import failed: ${String(e)}`);
    }
  };

  const selected = runHistory.find((r) => r.id === selectedRun) ?? null;
  const drift =
    selected && currentLibraryHash && currentDatasetHash
      ? driftKind(selected, currentLibraryHash, currentDatasetHash)
      : null;

  const runCompare = async () => {
    if (!currentArtifact) {
      setErr("run an evaluation first — the latest result is the compare target");
      return;
    }
    if (!selected) {
      setErr("select a prior run to compare against");
      return;
    }
    setRunning(true);
    setErr(null);
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

  return (
    <section className="pane evidence-pane" data-testid="evidence-pane">
      <div className="pane-header">
        <h2>Evidence</h2>
      </div>
      <div className="ev-controls">
        {(dataset?.resources ?? []).some(
          (r) =>
            (r as Record<string, unknown>).resourceType === "Patient",
        ) ? (
          <select
            data-testid="evidence-patient-input"
            value={patientId}
            onChange={(e) => setPatientId(e.target.value)}
            aria-label="patient id"
          >
            {(dataset?.resources ?? [])
              .filter(
                (r) =>
                  (r as Record<string, unknown>).resourceType === "Patient",
              )
              .map((r, i, arr) => {
                const p = r as Record<string, unknown>;
                const id = String(p.id ?? `#${i}`);
                const given = Array.isArray(
                  (p.name as Array<Record<string, unknown>> | undefined)?.[0]
                    ?.given,
                )
                  ? String(
                      (
                        (p.name as Array<Record<string, unknown>>)[0]
                          .given as unknown[]
                      )[0] ?? "",
                    )
                  : "";
                return (
                  <option key={`${id}-${i}`} value={id}>
                    {given ? `${id} — ${given}` : id}
                    {arr.length > 1 ? "" : ""}
                  </option>
                );
              })}
          </select>
        ) : (
          <input
            data-testid="evidence-patient-input"
            value={patientId}
            onChange={(e) => setPatientId(e.target.value)}
            placeholder="patient id"
            aria-label="patient id"
          />
        )}
        <button
          data-testid="explain-btn"
          onClick={runExplain}
          disabled={running || !dataset}
        >
          {running ? "working…" : "Explain"}
        </button>
        <button data-testid="import-evidence-btn" onClick={() => fileRef.current?.click()}>
          Import evidence.json
        </button>
        <input
          ref={fileRef}
          type="file"
          accept=".json"
          hidden
          onChange={(e) => {
            const f = e.target.files?.[0];
            if (f) void importEvidence(f);
            e.target.value = "";
          }}
        />
      </div>
      {err && <div className="ev-error" data-testid="evidence-error">{err}</div>}
      {env && !env.ok && (
        <div className="diag-list" data-testid="evidence-diags">
          {(env.diagnostics ?? []).map((d, i) => (
            <div key={i} className="diag-row diag-error">
              <span className="diag-code">{String(d.code)}</span>
              <span className="diag-msg">{d.message}</span>
            </div>
          ))}
        </div>
      )}
      <div className="ev-compare" data-testid="ev-compare">
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
      </div>
      {delta && (
        <div className="ev-delta" data-testid="compare-delta">
          {(delta.patients ?? []).length > 0 && (
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
          )}
        </div>
      )}
      {env?.ok && (
        <div className="ev-body" data-testid="evidence-body">
          <div className="ev-patient" data-testid="evidence-patient">
            {env.patient_id}
          </div>
          {Object.entries(env.populations ?? {}).map(([name, v]) => (
            <div key={name} className="ev-pop">
              <span className={`ev-badge ${v ? "ev-true" : "ev-false"}`} data-testid={`ev-pop-${name}`}>
                {String(v)}
              </span>
              <span className="ev-pop-name">{name}</span>
            </div>
          ))}
          {(env.definitions ?? []).map((def) => (
            <div key={def.column} className="ev-def" data-testid={`ev-def-${def.column}`}>
              <div className="ev-def-header">
                <span className={`ev-badge ${def.result ? "ev-true" : "ev-false"}`}>
                  {String(def.result)}
                </span>
                <span className="ev-def-name">{def.column}</span>
              </div>
              <EvidenceRows items={def.evidence as EvidenceItem[]} />
            </div>
          ))}
        </div>
      )}
    </section>
  );
}
