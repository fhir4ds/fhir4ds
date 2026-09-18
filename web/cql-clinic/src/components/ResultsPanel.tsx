import { useMemo } from "react";
import type { Lesson, LessonExpected } from "../lessons/types";
import { PatientDataViewer } from "./PatientDataViewer";

export interface DefineCheck {
  name: string;
  graded: boolean;
  pass: boolean | null; // null = no comparable row (e.g. missing column)
  expected: unknown;
  actual: unknown;
}

export interface GradeReport {
  columns: string[];
  rowsByPatient: Record<string, Record<string, unknown>>;
  checks: DefineCheck[];
  allPassed: boolean;
  /** Monotonic run counter — increments on every gradeResults call so
   *  downstream components (patient data viewer) can detect re-runs. */
  runId: number;
  /** Expected cell values keyed by patient then define name (per-patient grading + drill-down). */
  expectedByPatient: Record<string, Record<string, unknown>>;
  /** The lesson's expected patient ids in order. */
  expectedPatients: string[];
}

/** Normalize a cell for comparison: null/undefined unify; numbers compare
 *  numerically (Decimal scale differences like 3.5 vs "3.50000000" are
 *  value-equal, not string-equal); everything else stringified. */
function normalize(v: unknown): string | null {
  if (v === null || v === undefined) return null;
  if (typeof v === "number" && Number.isFinite(v)) return `num:${v}`;
  if (typeof v === "object") {
    try {
      return JSON.stringify(v);
    } catch {
      return String(v);
    }
  }
  const s = String(v);
  // A decimal-scale string from expected.json vs a JS number from Arrow:
  // compare numerically when both sides parse as finite numbers.
  if (/^-?\d+(\.\d+)?$/.test(s)) return `num:${Number(s)}`;
  return s;
}

/**
 * Compare actual query output against the lesson's expected output.
 * Grading matches by column NAME (the population SQL orders define columns
 * alphabetically; expected.columns mirrors that order).
 */
export function gradeResults(lesson: Lesson, result: { columns: string[]; rows: unknown[][] }): GradeReport {
  const expected: LessonExpected = lesson.expected;
  const patientIdIdx = result.columns.indexOf("patient_id");
  const rowsByPatient: Record<string, Record<string, unknown>> = {};
  for (const row of result.rows) {
    const pid = patientIdIdx >= 0 ? String(row[patientIdIdx]) : "_";
    const cells: Record<string, unknown> = {};
    result.columns.forEach((col, i) => {
      if (col !== "patient_id") cells[col] = row[i];
    });
    rowsByPatient[pid] = cells;
  }

  const checks: DefineCheck[] = expected.columns.map((name, colIdx) => {
    const graded = !lesson.ungradedDefines.includes(name);
    let pass: boolean | null = true;
    const expectedPatients = Object.keys(expected.rows);
    for (const pid of expectedPatients) {
      const expRow = expected.rows[pid];
      const expectedVal = expRow[colIdx];
      const actualVal = rowsByPatient[pid]?.[name];
      if (rowsByPatient[pid] === undefined) {
        pass = false;
        break;
      }
      if (normalize(expectedVal) !== normalize(actualVal)) {
        pass = false;
        break;
      }
    }
    // extra unexpected patients also fail graded defines
    if (pass === true) {
      const extraPatients = Object.keys(rowsByPatient).filter(
        (p) => p !== "_" && !(p in expected.rows),
      );
      if (extraPatients.length > 0) pass = false;
    }
    return {
      name,
      graded,
      pass: graded ? pass : null,
      expected: expectedPatients.length
        ? expected.rows[expectedPatients[0]][colIdx]
        : null,
      actual: rowsByPatient[expectedPatients[0] ?? "_"]?.[name],
    };
  });

  const gradedChecks = checks.filter((c) => c.graded);
  const allPassed = gradedChecks.length > 0 && gradedChecks.every((c) => c.pass === true);

  // Per-patient expected map for the patient-scoped checks table.
  const expectedByPatient: Record<string, Record<string, unknown>> = {};
  for (const pid of Object.keys(expected.rows)) {
    const cells: Record<string, unknown> = {};
    expected.columns.forEach((name, i) => { cells[name] = expected.rows[pid][i]; });
    expectedByPatient[pid] = cells;
  }

  gradeRunCounter += 1;
  return {
    columns: result.columns,
    rowsByPatient,
    checks,
    allPassed,
    runId: gradeRunCounter,
    expectedByPatient,
    expectedPatients: Object.keys(expected.rows),
  };
}

/** Module-scope counter incremented per gradeResults call. */
let gradeRunCounter = 0;

/** Resource types a define's CQL reads (for the failed-check drill-down).
 *  Scans the lesson CQL for retrieve expressions `[ResourceType]` and
 *  `Context <Type>` — a coarse but reliable lineage signal. */
export function retrieveTypesForDefine(cql: string, defineName: string): string[] {
  // Find the define block: from `define "<name>"` to the next `define` or EOF
  const re = new RegExp(
    `define\\s+"${defineName.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}"([\\s\\S]*?)(?=\\ndefine\\s|"\\n\\s*end\\b|$)`,
    "i",
  );
  const m = cql.match(re);
  if (!m) return [];

  // Collect direct retrieves, then follow quoted define references transitively
  // (composite defines like `"A" and "B"` should drill into the retrieves
  // their referenced defines read). Bounded depth guards against cycles.
  const types = new Set<string>();
  const visited = new Set<string>([defineName]);
  const queue: { body: string; depth: number }[] = [{ body: m[1], depth: 0 }];

  while (queue.length > 0) {
    const { body, depth } = queue.shift()!;
    for (const r of body.matchAll(/\[\s*([A-Z][A-Za-z]+)\s*\]/g)) types.add(r[1]);
    const ctx = body.match(/\b(?:from|Context)\s+([A-Z][A-Za-z]+)\b/);
    if (ctx) types.add(ctx[1]);
    if (depth >= 8) continue;
    for (const ref of body.matchAll(/"([A-Za-z][A-Za-z0-9 _'-]*)"/g)) {
      const name = ref[1];
      if (visited.has(name) || name === defineName) continue;
      visited.add(name);
      const child = cql.match(
        new RegExp(`define\\s+"${name.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}"([\\s\\S]*?)(?=\\ndefine\\s|"\\n\\s*end\\b|$)`, "i"),
      );
      if (child) queue.push({ body: child[1], depth: depth + 1 });
    }
  }
  return [...types];
}

export interface Drill {
  define: string;
  types: string[];
  patientId: string;
}

export type ResultsTab = "checks" | "sql" | "patient";

interface Props {
  running: boolean;
  error: string | null;
  report: GradeReport | null;
  /** Last run's timings, shown in the pane footer. */
  translateTimeMs: number | null;
  executionTimeMs: number | null;
  result: { columns: string[]; rows: unknown[][] } | null;
  /** Lesson fixtures (for patient/resource derivation). */
  fixtures: unknown[];
  /** Full lesson CQL (solution preferred) for retrieve-type drill-down. */
  lessonCql: string;
  /** DuckDB query interface for the patient data viewer. */
  executeQuery: (sql: string) => Promise<any>;
  duckdbReady: boolean;
  /** Generated SQL from the last run, for the SQL tab. */
  sql: string | null;
  /** Active right-pane tab + switcher. */
  activeTab: ResultsTab;
  onTabChange: (tab: ResultsTab) => void;
  /** Shared patient selection (Checks + Patient tabs stay in sync). */
  selectedPatient: string;
  onSelectPatient: (patientId: string) => void;
  /** Active failed-check drill-down (highlights resources in Patient tab). */
  drill: Drill | null;
  onDrillChange: (drill: Drill | null) => void;
}

/** Shared per-tab empty state: one wording pattern before the first run. */
function TabEmptyState({ what }: { what: string }) {
  return (
    <div className="empty-state">
      <span className="loading-spinner" />
      <span>{what} will appear here as you type — every run grades your CQL against the lesson patients.</span>
    </div>
  );
}

function CellValue({ v }: { v: unknown }) {
  if (v === null || v === undefined) return <span className="null">null</span>;
  const text = typeof v === "object" ? JSON.stringify(v) : String(v);
  return <span title={text}>{text}</span>;
}

export default function ResultsPanel({
  running,
  error,
  report,
  translateTimeMs,
  executionTimeMs,
  result,
  fixtures,
  lessonCql,
  executeQuery,
  duckdbReady,
  sql,
  activeTab,
  onTabChange,
  selectedPatient,
  onSelectPatient,
  drill,
  onDrillChange,
}: Props) {

  /** Patient ids + display labels ("Johnson, Alice" — the same derivation
   *  the PatientDataViewer uses in its dropdown, so the two stay in sync). */
  const patients = useMemo(() => {
    const out: { id: string; label: string }[] = [];
    const seen = new Set<string>();
    for (const f of fixtures as any[]) {
      if (f?.resourceType !== "Patient" || !f.id || seen.has(f.id)) continue;
      seen.add(f.id);
      const family = f.name?.[0]?.family ?? "";
      const given = f.name?.[0]?.given?.[0] ?? "";
      const label = [family, given].filter(Boolean).join(", ") || f.id;
      out.push({ id: f.id, label });
    }
    return out;
  }, [fixtures]);

  const activePatient = selectedPatient || patients[0]?.id || "";
  const showAllPatients = activePatient === "__all__";

  const selectedCells = report && activePatient ? report.rowsByPatient[activePatient] : undefined;

  // Per-patient check pass state: same comparison as gradeResults, scoped
  // to the selected patient's row (expected vs actual for this patient).
  const patientChecks = useMemo(() => {
    if (!report) return [];
    return report.checks.map((c) => {
      let pass: boolean | null = null;
      if (c.graded && report.expectedPatients.includes(activePatient)) {
        const expectedVal = report.expectedByPatient[activePatient]?.[c.name];
        const actualVal = selectedCells?.[c.name];
        pass = normalize(expectedVal) === normalize(actualVal);
      } else if (c.graded && selectedCells) {
        // Patient not in expected.json (shouldn't happen post-grade) — compare to null.
        pass = normalize(null) === normalize(selectedCells[c.name]);
      }
      return { ...c, pass };
    });
  }, [report, selectedCells, activePatient]);

  const tabBtn = (tab: ResultsTab, label: string) => (
    <button
      className={`tab-btn${activeTab === tab ? " tab-btn--active" : ""}`}
      onClick={() => onTabChange(tab)}
    >
      {label}
    </button>
  );

  return (
    <div className="panel results">
      <div className="tab-bar" role="tablist">
        {tabBtn("checks", `Checks${report ? ` (${report.checks.filter((c) => c.graded && c.pass).length}/${report.checks.filter((c) => c.graded).length})` : ""}`)}
        {tabBtn("sql", "Generated SQL")}
        {tabBtn("patient", "Patient Data")}
      </div>

      {activeTab === "checks" && (
        <div className="tab-content">
          {!report && !error && <TabEmptyState what="Your checks" />}

          {report && (
            <div className="patient-section">
              <div className="patient-picker">
                <select
                  id="patient-select"
                  aria-label="Test user"
                  value={activePatient}
                  onChange={(e) => { onSelectPatient(e.target.value); onDrillChange(null); }}
                >
                  {patients.map((p) => (
                    <option key={p.id} value={p.id}>{p.label}</option>
                  ))}
                  {patients.length > 1 && <option value="__all__">All patients (table)</option>}
                </select>
              </div>

              {!showAllPatients && (
              <table className="checks-table">
                <thead>
                  <tr>
                    <th>Check</th>
                    <th>Value</th>
                    <th>Result</th>
                  </tr>
                </thead>
                <tbody>
                  {patientChecks.map((c) => {
                    const value = selectedCells?.[c.name];
                    const failed = c.graded && c.pass === false;
                    const drillable = failed && retrieveTypesForDefine(lessonCql, c.name).length > 0;
                    return (
                      <tr
                        key={c.name}
                        className={`check-row ${failed ? "check-row-fail" : ""} ${drillable ? "check-row-drill" : ""}`}
                        onClick={drillable ? () =>
                          onDrillChange(drill?.define === c.name ? null : { define: c.name, types: retrieveTypesForDefine(lessonCql, c.name), patientId: activePatient })
                        : undefined}
                      >
                        <td>{c.name}</td>
                        <td className="checks-value"><CellValue v={value} /></td>
                        <td>
                          {!c.graded ? (
                            <span
                              className="meta"
                              title="Not graded — this define's value varies by run (e.g. Today() or the measurement period), so only its output is shown."
                              style={{ cursor: "help" }}
                            >
                              —
                            </span>
                          ) : c.pass ? (
                            <span className="pass-icon">✓</span>
                          ) : (
                            <span className="fail-icon">✗</span>
                          )}
                          {drillable && <span className="meta" style={{ marginLeft: 4 }}>why?</span>}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
              )}

              {drill && (
                <div className="drill-note">
                  <b>{drill.define}</b> reads <b>{drill.types.join(", ")}</b> for <b>{drill.patientId}</b>.
                  <button className="btn btn-ghost drill-jump" onClick={() => onTabChange("patient")}>
                    Inspect resources →
                  </button>
                </div>
              )}
            </div>
          )}

          {report && showAllPatients && result && (
            <div className="result-table-wrap">
              <table className="result-table">
                <thead>
                  <tr>
                    {result.columns.map((c) => (
                      <th key={c}>{c}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {result.rows.map((row, i) => (
                    <tr key={i}>
                      {row.map((v, j) => (
                        <td key={j}>
                          <CellValue v={v} />
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {activeTab === "sql" && (
        <div className="tab-content sql-tab">
          {sql ? (
            <pre className="sql-body">{sql}</pre>
          ) : (
            <TabEmptyState what="The SQL your CQL compiles to" />
          )}
        </div>
      )}

      {activeTab === "patient" && (
        <div className="tab-content">
          {!activePatient || showAllPatients ? (
            showAllPatients ? (
              <div className="meta" style={{ padding: "8px 10px" }}>
                Pick a single test user (Checks tab) to inspect their resources.
              </div>
            ) : (
              <TabEmptyState what="Patient data" />
            )
          ) : (
            <PatientDataViewer
              executeQuery={executeQuery}
              duckdbReady={duckdbReady}
              selectedPatientId={activePatient}
              onPatientSelect={(pid) => { if (pid !== activePatient) { onSelectPatient(pid); onDrillChange(null); } }}
              highlightTypes={drill?.types ?? null}
              dataVersion={report ? report.runId : 0}
            />
          )}
        </div>
      )}

      <div className="results-footer">
        {running && (
          <span className="status-running">
            <span className="loading-spinner" /> running…
          </span>
        )}
        {!running && report?.allPassed && (
          <span className="all-passed-inline">All checks passed — lesson complete! 🎉</span>
        )}
        {!running && error && (
          <span className="status-error" title={error}>
            {error.length > 90 ? error.slice(0, 90) + "…" : error}
          </span>
        )}
        {translateTimeMs !== null && executionTimeMs !== null && (
          <span className="meta results-footer__timings" title="last run — auto-runs 1.2s after you stop typing">
            translated {translateTimeMs.toFixed(1)} ms · executed {executionTimeMs.toFixed(1)} ms
          </span>
        )}
      </div>
    </div>
  );
}
