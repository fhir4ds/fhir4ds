import { useRef, useState } from "react";
import { workerRequest } from "./BootOverlay";
import type { CompareEvidenceResult } from "../lib/protocol";
import type { EvidenceResult, LibraryText } from "../lib/protocol";
import {
  PopulationSankey,
  buildPopulationFlow,
  type SankeyData,
} from "./PopulationSankey";

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
}: {
  libraries: LibraryText[];
  main: LibraryText;
  dataset: { resources: unknown[] } | null;
  outputColumns: Record<string, string>;
}) {
  const [patientId, setPatientId] = useState("p1");
  const [env, setEnv] = useState<EvidenceResult | null>(null);
  const [flow, setFlow] = useState<SankeyData | null>(null);
  const [running, setRunning] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  // C2-U3 Compare mode: baseline artifact JSON + delta envelope
  const [baseline, setBaseline] = useState<string>("");
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

  const buildFlow = async () => {
    if (!dataset) {
      setErr("load a dataset first");
      return;
    }
    setRunning(true);
    setErr(null);
    try {
      const resp = await workerRequest({
        type: "evaluate_library",
        libraries,
        main,
        dataset,
        output_columns: outputColumns,
      });
      const parsed = JSON.parse(resp.envelope);
      if (!parsed.ok) {
        setErr(parsed.diagnostics?.[0]?.message ?? "evaluation failed");
        return;
      }
      const columns = (parsed.columns as string[]).filter(
        (c) => c !== "patient_id",
      );
      setFlow(buildPopulationFlow(parsed.rows, columns));
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

  const runCompare = async () => {
    if (!env?.ok) {
      setErr("run Explain first — the current evidence is the compare target");
      return;
    }
    let baselinePayload: unknown;
    try {
      baselinePayload = baseline.trim() ? JSON.parse(baseline) : null;
    } catch (e) {
      setErr(`baseline is not valid JSON: ${String(e)}`);
      return;
    }
    if (!baselinePayload) {
      setErr("paste a baseline evidence artifact (JSON)");
      return;
    }
    setRunning(true);
    setErr(null);
    try {
      const resp = await workerRequest({
        type: "compare_evidence",
        baseline: baselinePayload,
        current: {
          patients: {
            [env.patient_id || "p1"]: { populations: env.populations ?? {} },
          },
        },
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
        <input
          data-testid="evidence-patient-input"
          value={patientId}
          onChange={(e) => setPatientId(e.target.value)}
          placeholder="patient id"
          aria-label="patient id"
        />
        <button
          data-testid="explain-btn"
          onClick={runExplain}
          disabled={running || !dataset}
        >
          {running ? "working…" : "Explain"}
        </button>
        <button data-testid="sankey-btn" onClick={buildFlow} disabled={running || !dataset}>
          Population flow
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
      {flow && <PopulationSankey data={flow} />}
      <div className="ev-compare" data-testid="ev-compare">
        <h3>Compare</h3>
        <textarea
          data-testid="compare-baseline"
          value={baseline}
          onChange={(e) => setBaseline(e.target.value)}
          placeholder='baseline evidence JSON, e.g. {"patients":{"p1":{"populations":{"IPP":true}}}}'
          rows={3}
        />
        <button data-testid="compare-run" onClick={runCompare} disabled={running}>
          Compare
        </button>
      </div>
      {delta && (
        <div className="ev-delta" data-testid="compare-delta">
          <div className="ev-delta-summary">
            <span className={`badge ${delta.changed ? "badge-changed" : "badge-clean"}`} data-testid="compare-changed">
              {delta.changed ? "CHANGED" : "no changes"}
            </span>
            {Object.entries(delta.summary ?? {}).map(([k, v]) =>
              v > 0 ? (
                <span key={k} className={`stat-chip delta-${k}`} data-testid={`compare-summary-${k}`}>
                  {k}: {v}
                </span>
              ) : null,
            )}
          </div>
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
