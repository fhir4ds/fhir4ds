import { useCallback, useEffect, useState } from "react";
import type { HttpTransport } from "./http-transport";

type PatientExpectation = {
  patient: string;
  report: Record<string, unknown>;
  groups: { id?: string; population: { code: string; count: number; display_id?: string }[] }[];
};

type CaptureResult = {
  ok: boolean;
  diagnostics: { message: string }[];
  measure?: string;
  reports?: Record<string, unknown>[];
  counts?: Record<string, number>;
};

type TestRunRow = {
  patient: string;
  code: string;
  expected: number | null;
  actual: number | null;
  pass: boolean;
  reason?: string;
};

type TestRunResult = {
  ok: boolean;
  diagnostics: { message: string }[];
  rows?: TestRunRow[];
  total?: number;
  passed?: number;
  failed?: number;
};

/**
 * S3b (c-cleanroom-ux5 item 3): EXPECTED-RESULTS EDITOR — the primary
 * test surface. Capture-from-run seeds per-patient expectations (in the
 * MADiE cqfm-test-cases shape), the grid edits expected counts, Run
 * diffs actual vs expected per patient/population. The old boolean
 * per-define grid is retired; define checks remain available through
 * the evaluate flow for non-measure libraries.
 */
export function ExpectedResultsPane({
  transport,
  library,
  buffer,
  measure,
  measureName,
}: {
  transport: HttpTransport;
  library: string;
  buffer: string;
  measure: Record<string, unknown> | null;
  measureName: string;
}) {
  const [expectations, setExpectations] = useState<PatientExpectation[]>([]);
  const [runResult, setRunResult] = useState<TestRunResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);

  const reload = useCallback(() => {
    if (!measureName) return;
    transport
      .testsExpectedGet(measureName)
      .then((r: { ok: boolean; patients?: PatientExpectation[]; diagnostics?: { message: string }[] }) => {
        if (r.ok) {
          setExpectations(r.patients ?? []);
        } else {
          setExpectations([]);
        }
      })
      .catch(() => setExpectations([]));
  }, [transport, measureName]);

  useEffect(() => {
    reload();
  }, [reload]);

  const capture = useCallback(async () => {
    if (!measure) {
      setError("No measure — scaffold or open a measure first.");
      return;
    }
    setBusy(true);
    setError(null);
    setMsg(null);
    try {
      const libs = [{ name: library, text: buffer }];
      const r: CaptureResult = await transport.testsCapture(libs, library, measure, measureName);
      if (!r.ok) {
        setError(r.diagnostics?.[0]?.message ?? "capture failed");
        return;
      }
      // Seed the editable grid from actuals (not yet persisted).
      setExpectations(
        (r.reports ?? []).map((rep) => ({
          patient: patientOf(rep),
          report: rep,
          groups: groupsOf(rep),
        })),
      );
      setMsg(`Captured ${r.reports?.length ?? 0} patients from the current run — edit, then Save expectations.`);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }, [transport, library, buffer, measure, measureName]);

  const save = useCallback(async () => {
    if (!expectations.length) return;
    setBusy(true);
    setError(null);
    setMsg(null);
    try {
      const reports = expectations.map((e) => withEditedGroups(e));
      const r = await transport.testsExpectedSave(measureName, reports);
      if (!r.ok) {
        setError(r.diagnostics?.[0]?.message ?? "save failed");
        return;
      }
      setMsg(`Saved ${r.count} expectation file(s) under measures/expected/patients/${measureName}/.`);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }, [transport, measureName, expectations]);

  const runTests = useCallback(async () => {
    if (!measure) {
      setError("No measure — scaffold or open a measure first.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const libs = [{ name: library, text: buffer }];
      const r: TestRunResult = await transport.testsRun(libs, library, measure, measureName);
      setRunResult(r);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }, [transport, library, buffer, measure, measureName]);

  const setCount = useCallback((patient: string, code: string, count: number) => {
    setExpectations((xs) =>
      xs.map((x) =>
        x.patient !== patient
          ? x
          : {
              ...x,
              groups: x.groups.map((g) => ({
                ...g,
                population: g.population.map((p) => (p.code === code ? { ...p, count } : p)),
              })),
            },
      ),
    );
  }, []);

  const removePatient = useCallback((patient: string) => {
    setExpectations((xs) => xs.filter((x) => x.patient !== patient));
    transport.testsExpectedDelete(measureName, patient).catch(() => undefined);
  }, [transport, measureName]);

  const codes = Array.from(
    new Set(expectations.flatMap((x) => x.groups.flatMap((g) => g.population.map((p) => p.code)))),
  );

  return (
    <div className="dev-testspane dev-expectedpane">
      <div className="dev-toolbar">
        <span
          className="dev-pane-label"
          title="Expected MeasureReport results per patient (MADiE cqfm-test-cases shape) — the primary test surface"
        >
          Expected results — {measureName || "no measure"}
        </span>
        <button
          disabled={busy || !measure}
          onClick={capture}
          title="Run the measure and seed per-patient expectations from the ACTUAL results"
        >
          ⬒ Capture from run
        </button>
        <button
          disabled={busy || expectations.length === 0}
          onClick={save}
          title="Persist expectations (one cqfm-test-cases MeasureReport per patient)"
        >
          Save expectations
        </button>
        <button
          disabled={busy || !measure}
          onClick={runTests}
          title="Evaluate and diff actual vs expected per patient/population"
        >
          ▶ Run tests
        </button>
      </div>
      {error && <div className="dev-vserror">{error}</div>}
      {msg && <div className="dev-vsimportmsg">{msg}</div>}
      {expectations.length === 0 && (
        <div className="dev-expectedempty">
          No expectations yet — Capture from run seeds the grid with actual results; edit and Save.
        </div>
      )}
      {expectations.length > 0 && (
        <div className="dev-expectedgrid">
          <div className="dev-expectedrow dev-expectedhead">
            <span>patient</span>
            {codes.map((c) => (
              <span key={c} title={`population ${c}`}>{c}</span>
            ))}
            <span />
          </div>
          {expectations.map((x) => (
            <div key={x.patient} className="dev-expectedrow">
              <span className="dev-expectedpatient" title={x.patient}>{x.patient}</span>
              {codes.map((c) => {
                const pop = x.groups.flatMap((g) => g.population).find((p) => p.code === c);
                return (
                  <input
                    key={c}
                    className="dev-expectedcount"
                    type="number"
                    min="0"
                    title={`expected ${c} count for ${x.patient}`}
                    value={pop ? String(pop.count) : "0"}
                    onChange={(e) =>
                      setCount(x.patient, c, Math.max(0, Number(e.target.value) || 0))
                    }
                  />
                );
              })}
              <button
                className="dev-expecteddel"
                title="Remove this patient's expectation (deletes the file)"
                onClick={() => removePatient(x.patient)}
              >
                ✕
              </button>
            </div>
          ))}
        </div>
      )}
      {runResult && (
        <div className={"dev-expectedrun " + (runResult.ok ? "pass" : "fail")}>
          <div className="dev-expectedrunhead">
            {runResult.ok
              ? `✔ all ${runResult.total} checks pass`
              : `✘ ${runResult.failed} of ${runResult.total} checks fail`}
          </div>
          {(runResult.rows ?? [])
            .filter((r) => !r.pass)
            .map((r, i) => (
              <div key={i} className="dev-expectedfail">
                {r.patient} · {r.code} — expected {r.expected ?? "—"}, actual {r.actual ?? "—"}
                {r.reason ? ` (${r.reason})` : ""}
              </div>
            ))}
        </div>
      )}
    </div>
  );
}

function patientOf(report: Record<string, unknown>): string {
  const subject = report["subject"] as { reference?: string } | undefined;
  const ref = subject?.reference ?? "";
  return ref.split("/").pop() ?? "";
}

function groupsOf(report: Record<string, unknown>): PatientExpectation["groups"] {
  const group = (report["group"] as PatientExpectation["groups"]) ?? [];
  return group.map((g) => ({
    id: g.id,
    population: (g.population ?? []).map((p) => ({
      code: String(p.code ?? ""),
      count: Number(p.count ?? 0),
    })),
  }));
}

function withEditedGroups(e: PatientExpectation): Record<string, unknown> {
  const out: Record<string, unknown> = { ...e.report };
  out["group"] = e.groups.map((g) => ({
    ...(g.id ? { id: g.id } : {}),
    population: g.population.map((p) => ({
      ...(p.display_id ? { id: p.display_id } : {}),
      code: p.code,
      count: p.count,
    })),
  }));
  return out;
}
