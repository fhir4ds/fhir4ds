import { useMemo, useState } from "react";
import type { HttpTransport } from "./http-transport";
import type { MeasureMappingEntry, MeasureScaffoldResult } from "./transport";

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
                  <span className="dev-mswarn" title="Run is disabled until initial-population is mapped">
                    {" "}UNMAPPED
                  </span>
                )}
              </td>
              <td>
                <select
                  value={rows[code] ?? ""}
                  onChange={(e) =>
                    setRows((prev) => ({ ...prev, [code]: e.target.value }))
                  }
                >
                  <option value="">—</option>
                  {definitions.map((d) => (
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
      {unmappedDefines.length > 0 && (
        <div className="dev-mschips">
          {unmappedDefines.map((d) => (
            <span key={d} className="dev-mschip" title="This define exists in the library but is not mapped to a population">
              {d} exists but unmapped — intentional?
            </span>
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
    </div>
  );
}
