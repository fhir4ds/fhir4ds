import { describe, expect, it } from "vitest";
import { deriveCompare } from "../../src/lib/verifyCompare";

describe("deriveCompare", () => {
  it("matches booleans per patient x population code", () => {
    const rows = [
      { patient_id: "p1", initial_population: true, numerator: true },
      { patient_id: "p2", initial_population: true, numerator: false },
    ];
    const expected = {
      p1: { "initial-population": true, numerator: true },
      p2: { "initial-population": true, numerator: true },
    };
    const r = deriveCompare(rows, expected, [
      "initial-population",
      "numerator",
    ]);
    expect(r.total).toBe(4);
    expect(r.passed).toBe(3);
    expect(r.rows[0].pid).toBe("p2"); // mismatch sorted first
    expect(r.rows[0].mismatch).toBe(true);
    expect(r.rows[0].cells[1]).toEqual({
      code: "numerator",
      expected: true,
      actual: false,
      match: false,
    });
    expect(r.rows[1].mismatch).toBe(false);
  });

  it("kebab-case codes join snake_case row columns", () => {
    const rows = [{ patient_id: "p1", denial_reason: true }];
    const r = deriveCompare(rows, { p1: { "denial-reason": true } }, [
      "denial-reason",
    ]);
    expect(r.passed).toBe(1);
  });

  it("marks patients absent from the actual run as mismatches", () => {
    const r = deriveCompare([], { p9: { "initial-population": true } }, [
      "initial-population",
    ]);
    expect(r.total).toBe(1);
    expect(r.passed).toBe(0);
    expect(r.rows[0].missing).toBe(true);
    expect(r.rows[0].cells[0].actual).toBeNull();
  });

  it("uncheckable expectation (expected false, no data) counts as pass", () => {
    const rows = [{ patient_id: "p1", initial_population: false }];
    const r = deriveCompare(rows, { p1: { "initial-population": false } }, [
      "initial-population",
    ]);
    expect(r.passed).toBe(1);
  });

  it("empty expectations yield 0/0", () => {
    expect(deriveCompare([{ patient_id: "p1" }], {}, ["initial-population"]))
      .toEqual({ total: 0, passed: 0, rows: [] });
  });
});
