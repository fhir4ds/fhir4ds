/**
 * 6h: expected-vs-actual comparison, DERIVED client-side.
 *
 * The heartbeat already evaluates every patient's population columns on
 * every edit — comparing authored expectations against the latest
 * library run is a pure join, so the compare recalcs automatically on
 * library edits, dataset changes, and checkbox flips with no second
 * engine round-trip (the run_tests capability remains worker-side but
 * the UI no longer needs it).
 */

export type ExpectedMap = { [patientId: string]: { [code: string]: boolean } };

export interface CompareCell {
  /** FHIR population code (expected-grid key, e.g. "initial-population"). */
  code: string;
  expected: boolean;
  /** boolean from the actual run; null = patient/column absent. */
  actual: boolean | null;
  match: boolean;
}

export interface CompareRow {
  pid: string;
  cells: CompareCell[];
  mismatch: boolean;
  /** Patient has no row in the actual run at all. */
  missing: boolean;
}

export interface CompareResult {
  /** checks = expected patients × population codes (run_tests parity). */
  total: number;
  passed: number;
  rows: CompareRow[];
}

/**
 * The measure's own population mapping: snake_case population column →
 * DEFINE name (criteria.expression). Library-run rows are keyed by define
 * name (full projection), so this is the only authority that resolves a
 * population code to its value — never a guessed column name.
 */
export type PopulationColumns = Record<string, string>;

export const populationColumnName = (code: string): string =>
  code.replace(/-/g, "_");

export function deriveCompare(
  rows: Array<Record<string, unknown>> | undefined,
  expected: ExpectedMap,
  populationCodes: string[],
  populationColumns: PopulationColumns | null,
): CompareResult {
  const byPatient = new Map<string, Record<string, unknown>>();
  for (const r of rows ?? []) {
    byPatient.set(String(r.patient_id ?? ""), r);
  }
  const out: CompareRow[] = [];
  let total = 0;
  let passed = 0;
  for (const [pid, codes] of Object.entries(expected)) {
    const actualRow = byPatient.get(pid);
    const cells: CompareCell[] = populationCodes.map((code) => {
      const exp = codes[code] === true;
      const define = populationColumns?.[populationColumnName(code)];
      const raw = define !== undefined ? actualRow?.[define] ?? null : null;
      const actual = typeof raw === "boolean" ? raw : null;
      const match = actual !== null && actual === exp;
      total += 1;
      if (match) passed += 1;
      return { code, expected: exp, actual, match };
    });
    out.push({
      pid,
      cells,
      mismatch: cells.some((c) => !c.match),
      missing: !actualRow,
    });
  }
  // Failures first, then alphabetical — mismatches visible without
  // scrolling.
  out.sort((a, b) =>
    a.mismatch === b.mismatch
      ? a.pid.localeCompare(b.pid)
      : a.mismatch
        ? -1
        : 1,
  );
  return { total, passed, rows: out };
}

/**
 * Library-run rows (define-named columns) → the rows MeasureReport
 * building expects: adds each population's snake_case column from the
 * measure's define mapping. Rows pass through unchanged without a mapping.
 */
export function populationRows(
  rows: Array<Record<string, unknown>>,
  columns: string[],
  populationColumns: PopulationColumns | null,
): { rows: Array<Record<string, unknown>>; columns: string[] } {
  if (!populationColumns) return { rows, columns };
  const popCols = Object.keys(populationColumns);
  const outRows = rows.map((r) => {
    const next: Record<string, unknown> = { ...r };
    for (const [col, define] of Object.entries(populationColumns)) {
      if (define in r) next[col] = r[define];
    }
    return next;
  });
  return {
    rows: outRows,
    columns: [...columns.filter((c) => !popCols.includes(c)), ...popCols],
  };
}
