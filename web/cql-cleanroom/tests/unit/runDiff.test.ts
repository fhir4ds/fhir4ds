import { describe, expect, it } from "vitest";
import {
  cellDiffClass,
  diffRuns,
  diffSummary,
} from "../../src/lib/runDiff";

const BASE = {
  p1: { ipp: true, num: false },
  p2: { ipp: false, num: false },
  p3: { ipp: true, num: true },
};

describe("diffRuns", () => {
  it("detects changed cells", () => {
    const cur = { ...BASE, p1: { ipp: false, num: false } };
    const d = diffRuns(cur, BASE)!;
    // key uses \u0000 separator — construct explicitly
    expect(d.cells.get(`p1\u0000ipp`)).toEqual({ from: true, to: false });
    expect(cellDiffClass(d, "p1", "ipp")).toBe("diff-down-cell");
    expect(cellDiffClass(d, "p2", "ipp")).toBeNull(); // unchanged
  });

  it("flags removed and added patients", () => {
    const cur = { ...BASE };
    delete (cur as Record<string, unknown>).p3;
    const d = diffRuns(cur as never, BASE)!;
    expect(d.removedPatients).toEqual(["p3"]);
    const d2 = diffRuns({ ...BASE, p9: { ipp: true } }, BASE)!;
    expect(d2.addedPatients).toEqual(["p9"]);
    expect(cellDiffClass(d2, "p9", "ipp")).toBe("diff-added-cell");
  });

  it("summary chips count", () => {
    const cur = {
      p1: { ipp: false }, // down
      p2: { ipp: true }, // up
      p4: { ipp: true }, // added patient
    };
    const base = { p1: { ipp: true }, p2: { ipp: false }, p3: { ipp: true } };
    const d = diffRuns(cur, base)!;
    const s = diffSummary(d);
    expect(s.changed).toBe(2);
    expect(s.added).toBe(1);
    expect(s.removed).toBe(1);
  });

  it("null baseline returns null", () => {
    expect(diffRuns(BASE, null)).toBeNull();
    expect(diffRuns(null, BASE)).toBeNull();
  });
});
