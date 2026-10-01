import { describe, it, expect } from "vitest";
import {
  normalizeCode,
  measurePopulations,
  deriveViewColumns,
  orphanedOverrides,
  buildDerivedView,
  type ViewOverrides,
} from "../../src/lib/viewDerivation";

const singleGroup = {
  resourceType: "Measure",
  group: [
    {
      id: "main",
      population: [
        {
          code: { coding: [{ code: "initial-population" }] },
          criteria: { expression: "Initial Population" },
        },
        {
          code: { coding: [{ code: "numerator" }] },
          criteria: { expression: "Has Name" },
        },
      ],
    },
  ],
};

const multiGroup = {
  resourceType: "Measure",
  group: [
    {
      id: "pharm",
      population: [
        {
          code: { coding: [{ code: "initial-population" }] },
          criteria: { expression: "Pharm IPP" },
        },
      ],
    },
    {
      id: "lab",
      population: [
        {
          code: { coding: [{ code: "initial-population" }] },
          criteria: { expression: "Lab IPP" },
        },
      ],
    },
  ],
};

describe("normalizeCode", () => {
  it("hyphenated codes become sql-name safe keys", () => {
    expect(normalizeCode("initial-population")).toBe("initial_population");
    expect(normalizeCode("numerator")).toBe("numerator");
  });
});

describe("measurePopulations", () => {
  it("extracts code+define pairs from all groups", () => {
    const pops = measurePopulations(singleGroup);
    expect(pops).toEqual([
      { code: "initial-population", define: "Initial Population" },
      { code: "numerator", define: "Has Name" },
    ]);
  });
  it("null measure yields empty", () => {
    expect(measurePopulations(null)).toEqual([]);
  });
});

describe("deriveViewColumns", () => {
  it("single group: one column per population with default path", () => {
    const cols = deriveViewColumns(singleGroup, null);
    expect(cols.map((c) => c.name)).toEqual([
      "initial_population",
      "numerator",
    ]);
    expect(cols[0].defaultPath).toBe(
      "group.where(population.code.coding.code='initial-population').population.count.first()",
    );
    expect(cols.every((c) => !c.overridden)).toBe(true);
  });

  it("multi-group measures prefix with sanitized group id (F3)", () => {
    const cols = deriveViewColumns(multiGroup, null);
    expect(cols.map((c) => c.name)).toEqual([
      "pharm_initial_population",
      "lab_initial_population",
    ]);
  });

  it("multi-group without ids falls back to g{N} prefix", () => {
    const noId = {
      group: multiGroup.group.map((g) => {
        const { id, ...rest } = g as Record<string, unknown>;
        void id;
        return rest;
      }),
    };
    const cols = deriveViewColumns(noId as Record<string, unknown>, null);
    expect(cols.map((c) => c.name)).toEqual([
      "g1_initial_population",
      "g2_initial_population",
    ]);
  });

  it("overrides fork name and path per normalized key", () => {
    const ov: ViewOverrides = {
      initial_population: { name: "ipp_count", path: "population[0].count" },
    };
    const cols = deriveViewColumns(singleGroup, ov);
    expect(cols[0].name).toBe("ipp_count");
    expect(cols[0].path).toBe("population[0].count");
    expect(cols[0].overridden).toBe(true);
    expect(cols[0].defaultName).toBe("initial_population");
    expect(cols[1].overridden).toBe(false);
  });

  it("blank-string overrides fall back to defaults (ghost text)", () => {
    const ov: ViewOverrides = { numerator: { name: "  ", path: "" } };
    const cols = deriveViewColumns(singleGroup, ov);
    expect(cols[1].name).toBe("numerator");
    expect(cols[1].path).toContain("population.count.first()");
    expect(cols[1].overridden).toBe(false);
  });
});

describe("orphanedOverrides", () => {
  it("flags keys with no live column (F7) without mutating", () => {
    const ov: ViewOverrides = {
      initial_population: { name: "x" },
      denominator: { name: "y" },
    };
    expect(orphanedOverrides(singleGroup, ov)).toEqual(["denominator"]);
  });
  it("empty when all keys live", () => {
    const ov: ViewOverrides = { numerator: { name: "n" } };
    expect(orphanedOverrides(singleGroup, ov)).toEqual([]);
  });
});

describe("buildDerivedView", () => {
  it("wide-format VD: one row per patient — patient_id + per-population integer columns, NO forEach", () => {
    const vd = buildDerivedView(singleGroup, null) as {
      resource: string;
      name: string;
      select: Array<{ column: Array<{ name: string; path: string; type: string }>; forEach?: string }>;
    };
    expect(vd.resource).toBe("MeasureReport");
    expect(vd.select[0].forEach).toBeUndefined();
    const names = vd.select[0].column.map((c) => c.name);
    expect(names).toEqual(["patient_id", "initial_population", "numerator"]);
    expect(vd.select[0].column[0].path).toBe("%resource.subject.reference");
    expect(vd.select[0].column[1].type).toBe("integer");
    expect(vd.select[0].column[1].path).toBe(
      "group.where(population.code.coding.code='initial-population').population.count.first()",
    );
  });

  it("multi-group prefixes names and scopes paths by group id", () => {
    const vd = buildDerivedView(multiGroup, null) as {
      select: Array<{ column: Array<{ name: string; path: string }> }>;
    };
    const names = vd.select[0].column.map((c) => c.name);
    expect(names).toEqual([
      "patient_id",
      "pharm_initial_population",
      "lab_initial_population",
    ]);
    expect(vd.select[0].column[1].path).toContain("group.where(id='pharm')");
  });

  it("applied overrides flow into the emitted VD", () => {
    const ov: ViewOverrides = { numerator: { name: "num" } };
    const vd = buildDerivedView(singleGroup, ov) as {
      select: Array<{ column: Array<{ name: string }> }>;
    };
    expect(vd.select[0].column.map((c) => c.name)).toContain("num");
  });
});
