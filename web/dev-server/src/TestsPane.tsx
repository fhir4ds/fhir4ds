import { useCallback, useEffect, useState } from "react";
import type { HttpTransport } from "./http-transport";
import type { VerifyResult } from "./transport";

type Case = {
  patient: string;
  target_kind: "population" | "define";
  target: string;
  expect: boolean;
  comment: string;
};

/**
 * Test-cases grid (v3 Slice 1): patient column is a dropdown fed by the
 * loaded dataset (never free text); expect is a true/false dropdown
 * (backend TestCase.expect is Boolean-only — population counts surface as
 * pass/fail against membership); Run posts the cases through /api/verify.
 */
export function TestsPane({
  transport,
  library,
  buffer,
  definitions,
  kernelId,
  patients,
}: {
  transport: HttpTransport;
  library: string;
  buffer: string;
  definitions: string[];
  kernelId: string;
  patients: string[];
}) {
  const [cases, setCases] = useState<Case[]>([]);
  const [paramsText, setParamsText] = useState("");
  const [result, setResult] = useState<VerifyResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const setCase = useCallback((i: number, patch: Partial<Case>) => {
    setCases((cs) => cs.map((c, j) => (j === i ? { ...c, ...patch } : c)));
  }, []);

  /** Parse 'Name = value' lines into a parameters map for /api/verify. */
  const parseParams = useCallback((text: string): Record<string, unknown> | undefined => {
    const out: Record<string, unknown> = {};
    for (const line of text.split("\n")) {
      const t = line.trim();
      if (!t) continue;
      const m = t.match(/^([A-Za-z][A-Za-z0-9_]*)\s*=\s*(.*)$/);
      if (!m) continue;
      const raw = m[2].trim();
      // typed literal: quoted string, number, boolean; else pass raw text
      let v: unknown = raw;
      if (/^'.*'$/.test(raw)) v = raw.slice(1, -1);
      else if (/^[+-]?\d+$/.test(raw)) v = parseInt(raw, 10);
      else if (/^[+-]?(\d+\.\d+|\.\d+)$/.test(raw)) v = parseFloat(raw);
      else if (raw === "true") v = true;
      else if (raw === "false") v = false;
      out[m[1]] = v;
    }
    return Object.keys(out).length ? out : undefined;
  }, []);

  const runTests = useCallback(async () => {
    setBusy(true);
    setError(null);
    setResult(null);
    try {
      const payload = cases.map((c) => {
        const body: Record<string, unknown> = { patient: c.patient, expect: c.expect };
        if (c.target_kind === "population") body.population = c.target;
        else body.define = c.target;
        if (c.comment.trim()) body.comment = c.comment.trim();
        return body;
      });
      const r = await transport.verify(
        [{ name: library, text: buffer }],
        library,
        payload,
        parseParams(paramsText),
      );
      setResult(r);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }, [transport, library, buffer, cases, paramsText, parseParams]);

  const tests = (result?.tests ?? {}) as {
    total?: number;
    passed?: number;
    failed?: number;
    failures?: { patient: string; target: string; expected: boolean; actual: string; reason: string }[];
  };

  return (
    <div className="dev-testspane">
      <div className="dev-toolbar">
        <span className="dev-pane-label">Test cases</span>
        <span>{library}</span>
        <button
          disabled={busy || cases.length === 0}
          onClick={runTests}
          title="Run every case against the loaded dataset"
        >
          ▶ Run tests
        </button>
        <button
          disabled={patients.length === 0}
          title="Add a case row (patient comes from the loaded dataset)"
          onClick={() =>
            setCases((cs) => [
              ...cs,
              {
                patient: patients[0] ?? "",
                target_kind: "define",
                target: definitions[0] ?? "",
                expect: true,
                comment: "",
              },
            ])
          }
        >
          + case
        </button>
      </div>
      {error && <div className="dev-vserror">{error}</div>}
      <div className="dev-testparams">
        <span className="dev-testparams-label" title="Overrides declared parameter defaults while running these cases (applies to ALL cases)">
          parameters
        </span>
        <textarea
          rows={2}
          placeholder={"Optional — one per line:\nMinAge = 21\nGender = 'male'"}
          value={paramsText}
          onChange={(e) => setParamsText(e.target.value)}
        />
      </div>
      <div className="dev-testgrid">
        <div className="dev-vsrow dev-vshead">
          <span>patient</span>
          <span>TARGET — what to check</span>
          <span>EXPECTED</span>
          <span>comment</span>
          <span />
        </div>
        {cases.length === 0 && (
          <div className="dev-vsempty">
            No cases yet — click “+ case”. Patients come from the loaded dataset.
          </div>
        )}
        {cases.map((c, i) => (
          <div key={i} className="dev-vsrow">
            <select value={c.patient} onChange={(e) => setCase(i, { patient: e.target.value })}>
              {patients.map((p) => (
                <option key={p} value={p}>
                  {p}
                </option>
              ))}
            </select>
            <span className="dev-testtarget">
              <select
                value={c.target_kind}
                onChange={(e) => setCase(i, { target_kind: e.target.value as Case["target_kind"] })}
              >
                <option value="define">define</option>
                <option value="population">population</option>
              </select>
              {c.target_kind === "define" ? (
                <select value={c.target} onChange={(e) => setCase(i, { target: e.target.value })}>
                  {[...new Set([...definitions, c.target])].filter(Boolean).map((d) => (
                    <option key={d} value={d}>
                      {d}
                    </option>
                  ))}
                </select>
              ) : (
                <select value={c.target} onChange={(e) => setCase(i, { target: e.target.value })}>
                  {["Initial Population", "Denominator", "Numerator", "Denominator Exclusion", "Denominator Exception", "Numerator Exclusion"].map((p) => (
                    <option key={p} value={p}>
                      {p}
                    </option>
                  ))}
                </select>
              )}
            </span>
            <select
              value={String(c.expect)}
              onChange={(e) => setCase(i, { expect: e.target.value === "true" })}
              title="Expected result for this patient's TARGET (Boolean membership — the runner checks the patient's row)"
            >
              <option value="true">true</option>
              <option value="false">false</option>
            </select>
            <input
              value={c.comment}
              placeholder="why"
              onChange={(e) => setCase(i, { comment: e.target.value })}
            />
            <button
              disabled={busy}
              title="Remove this case"
              onClick={() => setCases((cs) => cs.filter((_, j) => j !== i))}
            >
              ✕
            </button>
          </div>
        ))}
      </div>
      {result && (
        <div className="dev-testresults">
          <div className={"dev-testsummary " + (result.ok && result.passed ? "pass" : "fail")}>
            {result.ok && result.passed
              ? `✓ all ${tests.total ?? cases.length} cases pass`
              : `✗ ${tests.failed ?? 0} of ${tests.total ?? cases.length} cases fail`}
          </div>
          {(tests.failures ?? []).map((f, i) => (
            <div key={i} className="dev-testfail">
              <strong>{f.patient}</strong> · {f.target}: expected {String(f.expected)}, got {f.actual}
              {f.reason ? ` — ${f.reason}` : ""}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
