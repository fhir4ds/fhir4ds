import { useEffect, useMemo, useRef, useState } from "react";
import type { HttpTransport } from "./http-transport";
import type {
  DefineTypeInfo,
  MeasureCompareResult,
  MeasureMappingEntry,
  MeasureScaffoldResult,
} from "./transport";

/** Canonical FHIR measure-population codes (must match the server's POPULATION_ORDER). */
const POPULATIONS = [
  "initial-population",
  "denominator",
  "denominator-exclusion",
  "denominator-exception",
  "numerator",
  "numerator-exclusion",
  "measure-population",
  "measure-population-exclusion",
] as const;

const SCORINGS = ["proportion", "ratio", "continuous-variable", "cohort"] as const;

/**
 * Measure scaffold preview + run (v3 Slice 2). The mapping table is the
 * writer; the Measure JSON is a read-only PREVIEW (never auto-saved). Run
 * is disabled until scoring is set and initial-population is mapped.
 */
export function MeasurePane({
  transport,
  library,
  buffer,
  definitions,
}: {
  transport: HttpTransport;
  library: string;
  buffer: string;
  definitions: string[];
}) {
  const [rows, setRows] = useState<Record<string, string>>({});
  const [scoring, setScoring] = useState("");
  const [measureName, setMeasureName] = useState("CleanroomMeasure");
  const [preview, setPreview] = useState<MeasureScaffoldResult | null>(null);
  const [showRaw, setShowRaw] = useState(false);
  const [runResult, setRunResult] = useState<{
    ok: boolean;
    counts: Record<string, number>;
    reports: Record<string, unknown>[];
    error?: string;
  } | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [types, setTypes] = useState<DefineTypeInfo[]>([]);
  const rowRefs = useRef<Record<string, HTMLSelectElement | null>>({});
  const [expectedText, setExpectedText] = useState("");
  const [strict, setStrict] = useState(false);
  const [showExpectedRaw, setShowExpectedRaw] = useState(false);
  const [compareResult, setCompareResult] = useState<MeasureCompareResult | null>(null);

  const booleanDefines = useMemo(() => types.filter((t) => t.boolean).map((t) => t.name), [types]);
  const hiddenDefines = useMemo(
    () => definitions.filter((d) => !booleanDefines.includes(d)),
    [definitions, booleanDefines],
  );

  useEffect(() => {
    let cancelled = false;
    transport
      .defineTypes(library, buffer)
      .then((t) => {
        if (!cancelled) setTypes(t);
      })
      .catch(() => {
        // untyped fallback: show all defines as non-boolean-hidden
        if (!cancelled) setTypes(definitions.map((d) => ({ name: d, cql_type: null, boolean: true })));
      });
    return () => {
      cancelled = true;
    };
    // refetch when the library or buffer identity changes (buffer = client-authoritative)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [library, transport]);

  const mappedCodes = useMemo(
    () => new Set(Object.entries(rows).filter(([, d]) => d).map(([c]) => c)),
    [rows],
  );
  const mappedDefines = useMemo(
    () => new Set(Object.values(rows).filter(Boolean)),
    [rows],
  );
  const ipMapped = Boolean(rows["initial-population"]);
  const canRun = scoring !== "" && ipMapped && definitions.length > 0;
  const unmappedDefines = definitions.filter((d) => !mappedDefines.has(d));
  const firstUnmappedCode = POPULATIONS.find(
    (c) => c === "initial-population" && !rows[c],
  ) ?? null;

  function focusRow(code: string) {
    const sel = rowRefs.current[code];
    if (sel) {
      sel.focus();
      sel.scrollIntoView({ behavior: "smooth", block: "center" });
    }
  }

  function mappingPayload(): MeasureMappingEntry[] {
    return Object.entries(rows)
      .filter(([, define]) => define)
      .map(([code, define]) => ({ code, define }));
  }

  async function scaffold() {
    setBusy(true);
    setError(null);
    try {
      const libs = [{ name: library, text: buffer }];
      const r = await transport.measureScaffold(
        libs,
        library,
        mappingPayload(),
        scoring === "" ? undefined : scoring,
        measureName || undefined,
      );
      if (!r.ok) {
        setError(r.diagnostics[0]?.message ?? "scaffold failed");
        setPreview(null);
      } else {
        setPreview(r);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function run() {
    setBusy(true);
    setError(null);
    setRunResult(null);
    try {
      const libs = [{ name: library, text: buffer }];
      const s = await transport.measureScaffold(
        libs,
        library,
        mappingPayload(),
        scoring === "" ? undefined : scoring,
        measureName || undefined,
      );
      if (!s.ok || !s.measure) {
        setError(s.diagnostics[0]?.message ?? "scaffold failed");
        return;
      }
      setPreview(s);
      const r = await transport.measureRun(libs, library, s.measure);
      if (!r.ok) {
        setRunResult({
          ok: false,
          counts: {},
          reports: [],
          error: r.diagnostics[0]?.message ?? "run failed",
        });
      } else {
        setRunResult({ ok: true, counts: r.counts, reports: r.reports });
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  function parseExpected(): Record<string, unknown>[] | null {
    const text = expectedText.trim();
    if (!text) return null;
    try {
      const parsed: unknown = JSON.parse(text);
      const arr = Array.isArray(parsed) ? parsed : [parsed];
      if (!arr.every((r) => r && typeof r === "object" && !Array.isArray(r))) return null;
      return arr as Record<string, unknown>[];
    } catch {
      return null;
    }
  }

  async function compare() {
    setBusy(true);
    setError(null);
    setCompareResult(null);
    try {
      const expected = parseExpected();
      if (!expected) {
        setError("Paste expected MeasureReport JSON (a single object or an array) first.");
        return;
      }
      const libs = [{ name: library, text: buffer }];
      const s = await transport.measureScaffold(
        libs,
        library,
        mappingPayload(),
        scoring === "" ? undefined : scoring,
        measureName || undefined,
      );
      if (!s.ok || !s.measure) {
        setError(s.diagnostics[0]?.message ?? "scaffold failed");
        return;
      }
      setPreview(s);
      const r = await transport.measureCompare(libs, library, s.measure, expected, strict);
      if (!r.ok) {
        setError(r.diagnostics[0]?.message ?? "compare failed");
        return;
      }
      setCompareResult(r);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="dev-mspane">
      <div className="dev-toolbar">
        <span className="dev-pane-label">Measure</span>
        <select
          value={scoring}
          onChange={(e) => setScoring(e.target.value)}
          title="FHIR measure scoring code"
        >
          <option value="">scoring…</option>
          {SCORINGS.map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </select>
        <input
          className="dev-msname"
          placeholder="measure name"
          value={measureName}
          onChange={(e) => setMeasureName(e.target.value)}
          title="Measure.name for the scaffold preview"
        />
        <button disabled={busy} onClick={scaffold} title="Generate the Measure resource PREVIEW (never auto-saved)">
          Scaffold preview
        </button>
        <button
          className="dev-msrun"
          disabled={busy || !canRun}
          onClick={run}
          title={
            canRun
              ? `Evaluate the mapped populations against the loaded dataset`
              : "Run needs a scoring code and an initial-population mapping"
          }
        >
          ▶ Run measure
        </button>
        {!canRun && (
          <span className="dev-msrunreason">
            Select scoring + map initial-population to run
          </span>
        )}
      </div>
      {error && <div className="dev-vserror">{error}</div>}
      <table className="dev-msgrid">
        <thead>
          <tr>
            <th>population</th>
            <th>define</th>
          </tr>
        </thead>
        <tbody>
          {POPULATIONS.map((code) => (
            <tr key={code} className={code === "initial-population" && !rows[code] ? "dev-msunmapped" : undefined}>
              <td>
                {code}
                {code === "initial-population" && !rows[code] && (
                  <button
                    className="dev-mswarn"
                    title="Run is disabled until initial-population is mapped — click to focus its dropdown"
                    onClick={() => focusRow(code)}
                  >
                    {" "}UNMAPPED
                  </button>
                )}
              </td>
              <td>
                <select
                  ref={(el) => {
                    rowRefs.current[code] = el;
                  }}
                  value={rows[code] ?? ""}
                  onChange={(e) =>
                    setRows((prev) => ({ ...prev, [code]: e.target.value }))
                  }
                >
                  <option value="">—</option>
                  {booleanDefines.map((d) => (
                    <option key={d} value={d}>
                      {d}
                    </option>
                  ))}
                </select>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
        {hiddenDefines.length > 0 && (
          <div className="dev-msnote">
            {hiddenDefines.length} non-Boolean define{hiddenDefines.length === 1 ? "" : "s"} hidden
            — only Boolean defines can be population members. {hiddenDefines.join(", ")}
          </div>
        )}
      {unmappedDefines.length > 0 && (
        <div className="dev-mschips">
          {unmappedDefines.map((d) => (
            <button
              key={d}
              className="dev-mschip"
              title="This define exists in the library but is not mapped — click to focus the first unmapped population row"
              onClick={() => focusRow(firstUnmappedCode ?? POPULATIONS[0])}
            >
              {d} exists but unmapped — intentional?
            </button>
          ))}
        </div>
      )}
      {preview?.measure && (
        <div className="dev-mspreview">
          <div className="dev-mspreview-head">
            <span>
              Measure preview: {String((preview.measure as { name?: unknown }).name ?? "")} ·{" "}
              {mappedCodes.size} population{mappedCodes.size === 1 ? "" : "s"} mapped
            </span>
            <button onClick={() => setShowRaw((s) => !s)}>
              {showRaw ? "Hide raw" : "Show raw"}
            </button>
          </div>
          {showRaw && (
            <pre className="dev-msraw">{JSON.stringify(preview.measure, null, 2)}</pre>
          )}
          {!showRaw && (
            <div className="dev-msnote">
              The Measure JSON is a read-only preview — the mapping table above is the writer.
            </div>
          )}
        </div>
      )}
      {runResult && (
        <div className="dev-msresults">
          {runResult.ok ? (
            <>
              <div className="dev-mssummary pass">
                ✓ {Object.entries(runResult.counts)
                  .map(([code, n]) => `${code.replace(/-/g, "_")}: ${n}`)
                  .join(" · ")}{" "}
                · {runResult.reports.length} MeasureReport
                {runResult.reports.length === 1 ? "" : "s"} (per-patient)
              </div>
              <table className="dev-mscounts">
                <thead>
                  <tr>
                    <th>population</th>
                    <th>count</th>
                  </tr>
                </thead>
                <tbody>
                  {Object.entries(runResult.counts).map(([code, n]) => (
                    <tr key={code}>
                      <td>{code}</td>
                      <td>{n}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </>
          ) : (
            <div className="dev-vserror">{runResult.error}</div>
          )}
        </div>
      )}
      <div className="dev-msexpected">
        <div className="dev-msexpected-head">
          <span className="dev-pane-label">Expected MeasureReports</span>
          <label className="dev-msstrict" title="Strict FHIR equality also requires an identical report count (one per patient), not just equal population counts">
            <input
              type="checkbox"
              checked={strict}
              onChange={(e) => setStrict(e.target.checked)}
            />{" "}
            strict FHIR equality
          </label>
          <button
            className="dev-mscompare"
            disabled={busy || !canRun || !parseExpected()}
            onClick={compare}
            title={
              canRun
                ? "Run the library + measure, then diff normalized population counts against the expected MeasureReports"
                : "Compare needs a scoring code and an initial-population mapping"
            }
          >
            ▶ Compare
          </button>
        </div>
        <textarea
          className="dev-msexpinput"
          placeholder='Paste expected MeasureReport JSON here (single object or array)…'
          value={expectedText}
          onChange={(e) => setExpectedText(e.target.value)}
          spellCheck={false}
        />
        <button className="dev-msrawtoggle" onClick={() => setShowExpectedRaw((s) => !s)}>
          {showExpectedRaw ? "Hide raw" : "Show raw"}
        </button>
        {showExpectedRaw && (
          <pre className="dev-msraw">{expectedText}</pre>
        )}
        {compareResult && (
          <div className="dev-msdiff">
            <div className={compareResult.passed ? "dev-mssummary pass" : "dev-mssummary fail"}>
              {compareResult.passed ? "✓ PASS" : "✗ FAIL"} ·{" "}
              {compareResult.strict ? "strict" : "loose"} comparison
            </div>
            {compareResult.expected_measure.canonical !== null &&
              !compareResult.expected_measure.matches && (
                <div className="dev-mscanonical">
                  ⚠ expected MeasureReports reference measure{" "}
                  {compareResult.expected_measure.canonical} — does not match the open Measure
                </div>
              )}
            <table className="dev-mscounts">
              <thead>
                <tr>
                  <th>population</th>
                  <th>expected</th>
                  <th>actual</th>
                  <th>delta</th>
                </tr>
              </thead>
              <tbody>
                {compareResult.rows.map((row) => (
                  <tr key={row.code} className={row.delta !== 0 ? "dev-msdiffrow" : undefined}>
                    <td>{row.code}</td>
                    <td>{row.expected}</td>
                    <td>{row.actual}</td>
                    <td>{row.delta}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
