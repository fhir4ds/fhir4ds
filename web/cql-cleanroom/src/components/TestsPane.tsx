import { useState } from "react";
import type { VerifyEnvelope, LibraryText } from "../lib/protocol";
import { workerRequest } from "./BootOverlay";

export function TestsPane({
  libraries,
  main,
  dataset,
  outputColumns,
}: {
  libraries: LibraryText[];
  main: LibraryText;
  dataset: { resources?: Record<string, unknown>[] } | null;
  outputColumns: Record<string, string> | null;
}) {
  const [casesText, setCasesText] = useState(DEFAULT_CASES);
  const [result, setResult] = useState<VerifyEnvelope | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function run() {
    setBusy(true);
    setError(null);
    try {
      const tests = JSON.parse(casesText);
      const resp = await workerRequest({
        type: "run_tests",
        libraries,
        main,
        dataset,
        tests,
        output_columns: outputColumns,
      });
      const env: VerifyEnvelope = JSON.parse(resp.envelope);
      setResult(env);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="pane" data-testid="tests-pane">
      <header className="pane-header">
        <h2>Tests</h2>
        <button onClick={run} disabled={busy} data-testid="run-tests">
          {busy ? "Running…" : "Run tests"}
        </button>
      </header>
      {error && (
        <div className="pane-error" data-testid="tests-error">
          {error}
        </div>
      )}
      <textarea
        className="cases-editor"
        data-testid="cases-editor"
        value={casesText}
        onChange={(e) => setCasesText(e.target.value)}
        spellCheck={false}
      />
      {result && (
        <div className="tests-summary" data-testid="tests-summary">
          <span className={result.passed ? "pass" : "fail"}>
            {result.tests.passed}/{result.tests.total} passed
          </span>
          {result.tests.failures.length > 0 && (
            <table className="failures-table" data-testid="failures-table">
              <thead>
                <tr>
                  <th>Patient</th>
                  <th>Target</th>
                  <th>Expected</th>
                  <th>Actual</th>
                  <th>Reason</th>
                </tr>
              </thead>
              <tbody>
                {result.tests.failures.map((f, i) => (
                  <tr key={i}>
                    <td>{f.patient}</td>
                    <td>{f.target}</td>
                    <td>{String(f.expected)}</td>
                    <td>{f.actual === null ? "—" : String(f.actual)}</td>
                    <td>{f.reason ?? ""}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}
    </section>
  );
}

const DEFAULT_CASES = JSON.stringify(
  {
    schema: 1,
    cases: [
      { patient: "p1", population: "IPP", expect: true },
      { patient: "p2", population: "IPP", expect: false },
    ],
  },
  null,
  2,
);
