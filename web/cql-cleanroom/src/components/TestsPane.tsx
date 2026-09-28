import { useEffect, useMemo, useRef, useState } from "react";
import type {
  LibraryText,
  MeasureRowsResult,
  VerifyEnvelope,
} from "../lib/protocol";
import { workerRequest } from "./BootOverlay";

/**
 * TestsPane v3 — the authored MeasureReport editor (REORG 6c).
 *
 * Expected results are AUTHORED, not a mirror of the dataset: the grid
 * lists only the patients added to the active measure's expected
 * MeasureReports (one individual MR per patient, count 1|0 per code).
 * "Add patient" curates subjects from the dataset; All true/false bulk-
 * authors every dataset patient. Import/export as MeasureReport bundles
 * (MADiE interop).
 */

interface ExpectedMap {
  [patientId: string]: { [populationCode: string]: boolean };
}

export function TestsPane({
  libraries,
  main,
  dataset,
  populationCodes,
  outputColumns,
  expectedValues,
  onExpectedValuesChange,
  measure,
  parameters,
  onVerifyResult,
}: {
  libraries: LibraryText[];
  main: LibraryText;
  dataset: { resources?: Record<string, unknown>[] } | null;
  populationCodes: string[];
  outputColumns: Record<string, string> | null;
  expectedValues: ExpectedMap | null;
  onExpectedValuesChange: (v: ExpectedMap | null) => void;
  measure: Record<string, unknown> | null;
  /** Runtime CQL parameters (e.g. Measurement Period) for the engine. */
  parameters: Record<string, unknown>;
  /** 6h: the compare result renders in the CONSOLE, not in this pane. */
  onVerifyResult: (r: VerifyEnvelope | null) => void;
}) {
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  const patients = useMemo(() => {
    const ids = new Set<string>();
    for (const r of dataset?.resources ?? []) {
      if (r?.resourceType === "Patient" && typeof r.id === "string") {
        ids.add(r.id);
      }
    }
    return [...ids].sort();
  }, [dataset]);

  const expected: ExpectedMap = expectedValues ?? {};

  // Authored subjects: the grid lists exactly these patients, sorted.
  const addedPatients = useMemo(
    () => Object.keys(expected).sort(),
    [expectedValues],
  );
  const addablePatients = useMemo(
    () => patients.filter((pid) => !(pid in expected)),
    [patients, expectedValues],
  );

  function addPatient(pid: string) {
    if (!pid || pid in expected) return;
    const row: { [code: string]: boolean } = {};
    for (const code of populationCodes) row[code] = false;
    onExpectedValuesChange({ ...expected, [pid]: row });
  }

  function removePatient(pid: string) {
    const next: ExpectedMap = {};
    for (const [p, codes] of Object.entries(expected)) {
      if (p !== pid) next[p] = codes;
    }
    onExpectedValuesChange(Object.keys(next).length ? next : null);
  }

  useEffect(() => {
    // Keep the grid consistent with the current population codes.
    const codes = new Set(populationCodes);
    let changed = false;
    const next: ExpectedMap = {};
    for (const [pid, codes2] of Object.entries(expected)) {
      const filtered: { [code: string]: boolean } = {};
      for (const [code, v] of Object.entries(codes2)) {
        if (codes.has(code)) {
          filtered[code] = v;
        } else {
          changed = true;
        }
      }
      next[pid] = filtered;
    }
    if (changed && expectedValues) {
      onExpectedValuesChange(next);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [populationCodes.join(",")]);

  function setExpected(pid: string, code: string, value: boolean) {
    const next: ExpectedMap = {
      ...expected,
      [pid]: { ...(expected[pid] ?? {}), [code]: value },
    };
    onExpectedValuesChange(next);
  }

  function setAll(value: boolean) {
    const next: ExpectedMap = {};
    for (const pid of patients) {
      const row: { [code: string]: boolean } = {};
      for (const code of populationCodes) row[code] = value;
      next[pid] = row;
    }
    onExpectedValuesChange(next);
  }

  async function run() {
    setBusy(true);
    setError(null);
    onVerifyResult(null);
    try {
      const cases = Object.entries(expected).flatMap(([pid, codes]) =>
        Object.entries(codes).map(([code, expect]) => ({
          patient: pid,
          // Case population targets the aliased output column key
          // (snake_case form of the FHIR code, matching output_columns).
          population: code.replace(/-/g, "_"),
          expect,
        })),
      );
      const tests = { schema: 1, cases };
      const resp = await workerRequest({
        type: "run_tests",
        libraries,
        main,
        dataset,
        tests,
        // Required CQL parameters (e.g. Measurement Period) must reach
        // the engine or run_tests fails on a declared-no-default param.
        parameters,
        output_columns: outputColumns,
      });
      const env = JSON.parse((resp as { envelope: string }).envelope) as VerifyEnvelope;
      // A failed run (e.g. CQL translate error) has no `tests` payload —
      // surface it as an error instead of crashing on result.tests.
      if (!env.ok) {
        setError(
          env.diagnostics?.map((d) => d.message).join("; ") ??
            "test run failed",
        );
        return;
      }
      onVerifyResult(env);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function exportReports() {
    setBusy(true);
    setError(null);
    try {
      // Build expected-value MeasureReports via the capability inverse
      // path: expected rows -> reports (expected=true membership).
      const rows = Object.entries(expected).map(([pid, codes]) => {
        const row: Record<string, unknown> = { patient_id: pid };
        for (const code of populationCodes) {
          row[code.replace(/-/g, "_")] = codes[code] === true;
        }
        return row;
      });
      const resp = await workerRequest({
        type: "measure_report_from_rows",
        measure: measure!,
        rows,
        columns: ["patient_id", ...populationCodes.map((c) => c.replace(/-/g, "_"))],
      });
      const envJson = (resp as { envelope: string }).envelope;
      const env = JSON.parse(envJson) as { ok: boolean; reports?: unknown[]; diagnostics?: Array<{ message: string }> };
      if (!env.ok) {
        setError(env.diagnostics?.map((d) => d.message).join("; ") ?? "export failed");
        return;
      }
      const bundle = {
        resourceType: "Bundle",
        type: "collection",
        entry: (env.reports ?? []).map((r) => ({ resource: r })),
      };
      const blob = new Blob([JSON.stringify(bundle, null, 2)], {
        type: "application/json",
      });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "expected-measure-reports.json";
      a.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function importReports(file: File) {
    setBusy(true);
    setError(null);
    try {
      const text = await file.text();
      const parsed = JSON.parse(text);
      const resp = await workerRequest({
        type: "rows_from_measure_reports",
        reports: parsed,
        population_codes: populationCodes,
      });
      const env: MeasureRowsResult = JSON.parse((resp as { envelope: string }).envelope);
      if (!env.ok && !env.rows.length) {
        setError(env.diagnostics?.map((d) => d.message).join("; ") ?? "import failed");
        return;
      }
      const colToCode = new Map(
        populationCodes.map((c) => [c.replace(/-/g, "_"), c]),
      );
      const next: ExpectedMap = {};
      for (const row of env.rows) {
        const pid = String(row.patient_id ?? "");
        if (!pid) continue;
        const codes: { [code: string]: boolean } = {};
        for (const [col, value] of Object.entries(row)) {
          const code = colToCode.get(col);
          if (code) codes[code] = value === true;
        }
        next[pid] = codes;
      }
      onExpectedValuesChange(next);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  const measureAvailable = populationCodes.length > 0 && !!measure;

  return (
    <section className="pane tests-scroll" data-testid="tests-pane">
      <header className="pane-header">
        <h2>Tests</h2>
        <div className="pane-actions">
          <select
            data-testid="expected-add-patient"
            value=""
            disabled={!measureAvailable || addablePatients.length === 0}
            onChange={(e) => {
              addPatient(e.target.value);
              e.target.value = "";
            }}
            title="Add a dataset patient to the expected MeasureReport"
          >
            <option value="">+ Add patient…</option>
            {addablePatients.map((pid) => (
              <option key={pid} value={pid}>
                {pid}
              </option>
            ))}
          </select>
          <button
            onClick={() => setAll(true)}
            disabled={!patients.length || !measureAvailable}
            data-testid="tests-set-all-true"
          >
            All true
          </button>
          <button
            onClick={() => setAll(false)}
            disabled={!patients.length || !measureAvailable}
            data-testid="tests-set-all-false"
          >
            All false
          </button>
          <button
            onClick={exportReports}
            disabled={busy || !measureAvailable}
            data-testid="tests-export"
          >
            Export reports
          </button>
          <button
            onClick={() => fileInputRef.current?.click()}
            disabled={busy || !measureAvailable}
            data-testid="tests-import"
          >
            Import reports
          </button>
          <button onClick={run} disabled={busy} data-testid="run-tests">
            {busy ? "Running…" : "Run tests"}
          </button>
          <input
            ref={fileInputRef}
            type="file"
            accept="application/json"
            style={{ display: "none" }}
            onChange={(e) => {
              const f = e.target.files?.[0];
              if (f) importReports(f);
              e.target.value = "";
            }}
            data-testid="tests-import-input"
          />
        </div>
      </header>
      {error && (
        <div className="pane-error" data-testid="tests-error">
          {error}
        </div>
      )}
      {!measureAvailable ? (
        <p className="pane-hint" data-testid="tests-no-measure">
          Define a Measure mapping first — expected values attach to
          population codes.
        </p>
      ) : (
        <div className="expected-grid-wrap">
        <table className="expected-grid" data-testid="expected-grid">
          <thead>
            <tr>
              <th>Patient</th>
              {populationCodes.map((c) => (
                <th key={c}>{c}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {addedPatients.map((pid) => (
              <tr key={pid} data-testid={`expected-row-${pid}`}>
                <td>
                  {pid}
                  <button
                    className="row-remove"
                    title="Remove this patient from the expected MeasureReport"
                    aria-label={`Remove ${pid}`}
                    onClick={() => removePatient(pid)}
                    data-testid={`expected-remove-${pid}`}
                  >
                    ×
                  </button>
                </td>
                {populationCodes.map((c) => {
                  const value = expected[pid]?.[c];
                  return (
                    <td key={c}>
                      <input
                        type="checkbox"
                        checked={value === true}
                        onChange={(e) => setExpected(pid, c, e.target.checked)}
                        data-testid={`expected-${pid}-${c}`}
                      />
                    </td>
                  );
                })}
              </tr>
            ))}
            {addedPatients.length === 0 && (
              <tr>
                <td colSpan={populationCodes.length + 1}>
                  <span className="pane-hint">
                    No patients in the expected report — add them above.
                  </span>
                </td>
              </tr>
            )}
          </tbody>
        </table>
        </div>
      )}
    </section>
  );
}
