import { describe, expect, it } from "vitest";
import {
  casesFromReports,
  expectedMapFromReports,
  expectedReportsFromCases,
  reportsFromExpectedMap,
} from "../../src/lib/expectedReports";

describe("expectedReports conversions (cases ⇄ MeasureReport ⇄ map)", () => {
  const CASES = [
    { patient: "p1", population: "initial-population", expect: true },
    { patient: "p1", population: "numerator", expect: false },
    { patient: "p2", population: "initial-population", expect: true },
  ];

  it("cases → one report per patient with count 0|1 populations", () => {
    const reports = expectedReportsFromCases(CASES);
    expect(reports).toHaveLength(2);
    expect(reports.every((r) => r.resourceType === "MeasureReport")).toBe(true);
    expect(reports.every((r) => r.type === "individual")).toBe(true);
    const p1 = reports.find(
      (r) => (r.subject as { reference: string }).reference === "Patient/p1",
    )!;
    const pops = (p1.group as Array<{ population: Array<Record<string, unknown>> }>)[0]
      .population as Array<{
      code: { coding: Array<{ code: string }> };
      count: number;
    }>;
    expect(
      pops.find((p) => p.code.coding[0].code === "initial-population")!.count,
    ).toBe(1);
    expect(pops.find((p) => p.code.coding[0].code === "numerator")!.count).toBe(0);
  });

  it("map → reports → map round-trips the TestsPane grid", () => {
    const map = {
      p1: { "initial-population": true, numerator: false },
      p2: { "initial-population": true },
    };
    const back = expectedMapFromReports(reportsFromExpectedMap(map));
    expect(back).toEqual(map);
  });

  it("reports → legacy cases keeps row form (v5 zip interop)", () => {
    const reports = expectedReportsFromCases(CASES);
    expect(casesFromReports(reports)).toEqual(CASES);
  });

  it("degenerate inputs yield empty/null, never throws", () => {
    expect(expectedReportsFromCases(null)).toEqual([]);
    expect(expectedReportsFromCases([{ patient: "x" }])).toEqual([]);
    expect(expectedMapFromReports([])).toBeNull();
    expect(expectedMapFromReports(null)).toBeNull();
    expect(reportsFromExpectedMap(null)).toEqual([]);
    expect(casesFromReports(undefined)).toEqual([]);
  });

  it("malformed case rows are skipped (no patient/population strings)", () => {
    expect(
      expectedReportsFromCases([
        { patient: "", population: "ip", expect: true },
        { patient: "p", population: "", expect: true },
        { patient: 42, population: "ip", expect: true },
      ]),
    ).toEqual([]);
  });
});
