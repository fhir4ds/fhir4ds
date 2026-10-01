import { describe, expect, it } from "vitest";
import {
  appendRun,
  artifactFromRows,
  canonicalJson,
  defaultRunName,
  driftKind,
  normalizeText,
} from "../../src/lib/runHistory";
import type { RunEntry } from "../../src/state/workspace";

describe("runHistory helpers (WORKBENCH_REORG §3.3)", () => {
  it("artifactFromRows builds row-shaped memberships, null-preserving", () => {
    const a = artifactFromRows(
      [
        { patient_id: "p1", initial_population: true, numerator: null },
        { patient_id: "p2", initial_population: false, numerator: true },
      ],
      ["patient_id", "initial_population", "numerator"],
    );
    expect(a.patients.p1.populations.initial_population).toBe(true);
    expect(a.patients.p1.populations.numerator).toBeNull();
    expect(a.patients.p2.populations.initial_population).toBe(false);
  });

  it("appendRun caps and prunes oldest", () => {
    const mk = (id: string): RunEntry => ({
      id,
      name: id,
      createdAt: 0,
      libraryHash: "h",
      datasetHash: "h",
      artifact: { patients: {} },
    });
    let h: RunEntry[] = [];
    for (let i = 0; i < 25; i++) h = appendRun(h, mk(`r${i}`), 20);
    expect(h.length).toBe(20);
    expect(h[0].id).toBe("r5");
    expect(h[h.length - 1].id).toBe("r24");
  });

  it("canonicalJson sorts keys recursively (property order irrelevant)", () => {
    expect(canonicalJson({ b: 1, a: { d: 2, c: 3 } })).toBe(
      '{"a":{"c":3,"d":2},"b":1}',
    );
  });

  it("normalizeText normalizes CRLF/CR to LF", () => {
    expect(normalizeText("a\r\nb\rc\nd")).toBe("a\nb\nc\nd");
  });

  it("driftKind flags per-input", () => {
    const run: RunEntry = {
      id: "r",
      name: "r",
      createdAt: 0,
      libraryHash: "lh",
      datasetHash: "dh",
      artifact: { patients: {} },
    };
    expect(driftKind(run, "lh", "dh")).toEqual({
      library: false,
      dataset: false,
    });
    expect(driftKind(run, "lh!", "dh")).toEqual({
      library: true,
      dataset: false,
    });
    expect(driftKind(run, "lh", "dh!")).toEqual({
      library: false,
      dataset: true,
    });
  });

  it("defaultRunName is full date+time", () => {
    const d = new Date(2026, 0, 1, 3, 4, 5).getTime();
    expect(defaultRunName(d)).toBe("2026-01-01 03:04:05");
  });
});
