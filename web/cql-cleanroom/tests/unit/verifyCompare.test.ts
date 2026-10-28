import { describe, expect, it } from "vitest";
import { deriveCompare, populationRows } from "../../src/lib/verifyCompare";

/** The measure's own population mapping (snake column → define), exactly
 *  what App.outputColumnsFromMeasure derives from criteria.expression. */
const CMS125_COLUMNS = {
  initial_population: "Initial Population",
  numerator: "Numerator",
};

describe("deriveCompare", () => {
  it("resolves population values through the measure's define mapping", () => {
    // Full-projection library-run rows are keyed by DEFINE name (what the
    // heartbeat returns), never by population code.
    const rows = [
      { patient_id: "p1", "Initial Population": true, Numerator: true },
      { patient_id: "p2", "Initial Population": true, Numerator: false },
    ];
    const expected = {
      p1: { "initial-population": true, numerator: true },
      p2: { "initial-population": true, numerator: true },
    };
    const r = deriveCompare(
      rows,
      expected,
      ["initial-population", "numerator"],
      CMS125_COLUMNS,
    );
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

  it("a population with no define mapping is unresolved, not silently false", () => {
    const rows = [{ patient_id: "p1", Numerator: true }];
    const r = deriveCompare(rows, { p1: { numerator: true } }, ["numerator"], null);
    expect(r.rows[0].cells[0].actual).toBeNull();
    expect(r.passed).toBe(0);
  });

  it("marks patients absent from the actual run as mismatches", () => {
    const r = deriveCompare([], { p9: { "initial-population": true } }, [
      "initial-population",
    ], CMS125_COLUMNS);
    expect(r.total).toBe(1);
    expect(r.passed).toBe(0);
    expect(r.rows[0].missing).toBe(true);
    expect(r.rows[0].cells[0].actual).toBeNull();
  });

  it("uncheckable expectation (expected false, no data) counts as pass", () => {
    const rows = [{ patient_id: "p1", "Initial Population": false }];
    const r = deriveCompare(
      rows,
      { p1: { "initial-population": false } },
      ["initial-population"],
      CMS125_COLUMNS,
    );
    expect(r.passed).toBe(1);
  });

  it("empty expectations yield 0/0", () => {
    expect(
      deriveCompare([{ patient_id: "p1" }], {}, ["initial-population"], CMS125_COLUMNS),
    ).toEqual({ total: 0, passed: 0, rows: [] });
  });
});

describe("populationRows", () => {
  it("adds snake_case population columns from the define mapping", () => {
    const out = populationRows(
      [{ patient_id: "p1", "Initial Population": true, Numerator: false }],
      ["patient_id", "Initial Population", "Numerator"],
      CMS125_COLUMNS,
    );
    expect(out.rows[0]).toMatchObject({
      patient_id: "p1",
      initial_population: true,
      numerator: false,
    });
    expect(out.columns).toEqual(
      expect.arrayContaining(["initial_population", "numerator"]),
    );
  });

  it("passes rows through untouched without a mapping", () => {
    const rows = [{ patient_id: "p1" }];
    expect(populationRows(rows, ["patient_id"], null)).toEqual({
      rows,
      columns: ["patient_id"],
    });
  });
});
