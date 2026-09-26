/**
 * Expected-results representation (WORKBENCH_V6): authored MeasureReport
 * resources replace the lossy pid→pop→bool "cases" map. All three shapes
 * stay interconvertible so legacy zips/cases keep importing:
 *
 *   cases rows  ⇄  MeasureReport[]  ⇄  expected map (TestsPane grid)
 *
 * Report shape matches measure_report_from_rows output exactly
 * (subject.reference, group[].population[].code.coding[0].code, count
 * 0|1) so rows_from_measure_reports consumes them unchanged — the same
 * count===1 ⇒ true semantics as measureBundle.ts.
 */

export interface CaseRow {
  patient?: string;
  population?: string;
  expect?: boolean;
}

export type ExpectedMap = { [pid: string]: { [code: string]: boolean } };

/** Legacy case rows → one authored MeasureReport per patient. */
export function expectedReportsFromCases(
  cases: unknown[] | null | undefined,
): Array<Record<string, unknown>> {
  const byPatient = new Map<string, Array<{ code: string; expect: boolean }>>();
  for (const raw of cases ?? []) {
    const c = raw as CaseRow;
    if (typeof c?.patient !== "string" || typeof c?.population !== "string") {
      continue;
    }
    if (!c.patient || !c.population) continue;
    const list = byPatient.get(c.patient) ?? [];
    list.push({ code: c.population, expect: c.expect === true });
    byPatient.set(c.patient, list);
  }
  const reports: Array<Record<string, unknown>> = [];
  for (const [pid, pops] of byPatient) {
    reports.push(expectedReportFor(pid, pops));
  }
  return reports;
}

/** Authored single-patient expected MeasureReport (count 0|1 per code). */
export function expectedReportFor(
  pid: string,
  pops: Array<{ code: string; expect: boolean }>,
): Record<string, unknown> {
  return {
    resourceType: "MeasureReport",
    status: "complete",
    type: "individual",
    measure: "urn:cleanroom:measure",
    subject: { reference: `Patient/${pid}` },
    group: [
      {
        population: pops.map((p) => ({
          code: { coding: [{ code: p.code }] },
          count: p.expect ? 1 : 0,
        })),
      },
    ],
  };
}

/**
 * MeasureReports → the TestsPane expected map (mirror of the
 * measureBundle.ts importer: population count 1 = true, others false).
 */
export function expectedMapFromReports(
  reports: Array<Record<string, unknown>> | null | undefined,
): ExpectedMap | null {
  if (!reports?.length) return null;
  const out: ExpectedMap = {};
  for (const r of reports) {
    const pid =
      ((r.subject as Record<string, unknown> | undefined)?.reference as
        | string
        | undefined)
        ?.split("/")
        .pop() ?? "";
    if (!pid) continue;
    const memberships: Record<string, boolean> = {};
    for (const g of (r.group as Array<Record<string, unknown>>) ?? []) {
      for (const pop of (g.population as Array<Record<string, unknown>>) ?? []) {
        const code =
          ((pop.code as { coding?: Array<{ code?: string }> })?.coding ?? [])[0]
            ?.code ?? "";
        if (code) memberships[code] = (pop.count as number) === 1;
      }
    }
    out[pid] = memberships;
  }
  return Object.keys(out).length ? out : null;
}

/** TestsPane expected map → authored MeasureReports (grid is the UI form). */
export function reportsFromExpectedMap(
  map: ExpectedMap | null | undefined,
): Array<Record<string, unknown>> {
  if (!map) return [];
  return Object.entries(map).map(([pid, codes]) =>
    expectedReportFor(
      pid,
      Object.entries(codes).map(([code, expect]) => ({ code, expect })),
    ),
  );
}

/** Authored MeasureReports → legacy case rows (v6 save keeps cases in sync). */
export function casesFromReports(
  reports: Array<Record<string, unknown>> | null | undefined,
): Array<CaseRow> {
  const rows: Array<CaseRow> = [];
  for (const r of reports ?? []) {
    const pid =
      ((r.subject as Record<string, unknown> | undefined)?.reference as
        | string
        | undefined)
        ?.split("/")
        .pop() ?? "";
    if (!pid) continue;
    for (const g of (r.group as Array<Record<string, unknown>>) ?? []) {
      for (const pop of (g.population as Array<Record<string, unknown>>) ?? []) {
        const code =
          ((pop.code as { coding?: Array<{ code?: string }> })?.coding ?? [])[0]
            ?.code ?? "";
        if (code) rows.push({ patient: pid, population: code, expect: (pop.count as number) === 1 });
      }
    }
  }
  return rows;
}
