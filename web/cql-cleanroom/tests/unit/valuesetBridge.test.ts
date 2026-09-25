import { describe, expect, it } from "vitest";
import { seedValuesetCache, valuesetToRows } from "../../src/lib/valuesetBridge";

const VS = (over: Record<string, unknown> = {}) => ({
  resourceType: "ValueSet",
  url: "http://example.org/vs/genders",
  compose: {
    include: [
      {
        system: "http://hl7.org/fhir/administrative-gender",
        concept: [
          { code: "female", display: "Female" },
          { code: "male", display: "Male" },
        ],
      },
    ],
  },
  ...over,
});

describe("valuesetToRows", () => {
  it("flattens compose.include.concept rows", () => {
    const { rows, warnings } = valuesetToRows([VS()]);
    expect(warnings).toEqual([]);
    expect(rows).toEqual([
      {
        url: "http://example.org/vs/genders",
        system: "http://hl7.org/fhir/administrative-gender",
        code: "female",
      },
      {
        url: "http://example.org/vs/genders",
        system: "http://hl7.org/fhir/administrative-gender",
        code: "male",
      },
    ]);
  });

  it("falls back to expansion.contains when compose absent", () => {
    const { rows } = valuesetToRows([
      {
        resourceType: "ValueSet",
        url: "urn:vs:exp",
        expansion: {
          contains: [{ system: "urn:s", code: "a" }, { system: "urn:s", code: "b" }],
        },
      },
    ]);
    expect(rows.map((r) => r.code)).toEqual(["a", "b"]);
  });

  it("seeds the deterministic-FALSE sentinel for empty ValueSets", () => {
    const { rows } = valuesetToRows([
      { resourceType: "ValueSet", url: "urn:vs:empty", compose: { include: [] } },
    ]);
    expect(rows).toEqual([
      { url: "urn:vs:empty", system: "urn:cleanroom:empty", code: "__EMPTY_VALUESET__" },
    ]);
  });

  it("dedupes repeated codes across overlapping includes", () => {
    const { rows } = valuesetToRows([
      {
        resourceType: "ValueSet",
        url: "urn:vs:1",
        compose: {
          include: [
            { system: "urn:s", concept: [{ code: "x" }] },
            { system: "urn:s", concept: [{ code: "x" }, { code: "y" }] },
          ],
        },
      },
    ]);
    expect(rows.map((r) => r.code)).toEqual(["x", "y"]);
  });

  it("skips concepts without a system and warns", () => {
    const { rows, warnings } = valuesetToRows([
      {
        resourceType: "ValueSet",
        url: "urn:vs:nosys",
        compose: { include: [{ concept: [{ code: "z" }] }] },
      },
    ]);
    expect(rows).toEqual([
      { url: "urn:vs:nosys", system: "urn:cleanroom:empty", code: "__EMPTY_VALUESET__" },
    ]);
    expect(warnings[0]).toContain("no system");
  });

  it("warns on compose.exclude (known engine boundary)", () => {
    const { warnings } = valuesetToRows([
      {
        resourceType: "ValueSet",
        url: "urn:vs:ex",
        compose: {
          include: [{ system: "urn:s", concept: [{ code: "a" }] }],
          exclude: [{ system: "urn:s", concept: [{ code: "a" }] }],
        },
      },
    ]);
    expect(warnings.some((w) => w.includes("compose.exclude"))).toBe(true);
  });

  it("warns on filter/valueSet imports and url-less ValueSets", () => {
    const { rows, warnings } = valuesetToRows([
      {
        resourceType: "ValueSet",
        url: "urn:vs:imp",
        compose: { include: [{ system: "urn:s", valueSet: ["urn:other"] }] },
      },
      { resourceType: "ValueSet" },
    ]);
    expect(rows).toEqual([
      { url: "urn:vs:imp", system: "urn:cleanroom:empty", code: "__EMPTY_VALUESET__" },
    ]);
    expect(warnings.some((w) => w.includes("filter/valueSet"))).toBe(true);
    expect(warnings.some((w) => w.includes("without a url"))).toBe(true);
  });
});

describe("seedValuesetCache", () => {
  it("clears then stages rows vectorized (statement order)", async () => {
    const stmts: string[] = [];
    await seedValuesetCache(
      [
        { url: "urn:vs:1", system: "urn:s", code: "a" },
        { url: "urn:vs:1", system: "urn:s", code: "b" },
      ],
      async (sql) => {
        stmts.push(sql);
      },
    );
    expect(stmts[0]).toBe("SELECT cql_valueset_cache_clear()");
    expect(stmts[1]).toContain("CREATE OR REPLACE TEMP TABLE __cleanroom_vs_stage");
    expect(stmts[2]).toContain("('urn:vs:1', 'urn:s', 'a'), ('urn:vs:1', 'urn:s', 'b')");
    expect(stmts[3]).toBe(
      "SELECT cql_valueset_cache_add(url, system, code) FROM __cleanroom_vs_stage",
    );
    expect(stmts[4]).toBe("DROP TABLE __cleanroom_vs_stage");
  });

  it("empty row set clears the cache only", async () => {
    const stmts: string[] = [];
    await seedValuesetCache([], async (sql) => {
      stmts.push(sql);
    });
    expect(stmts).toEqual(["SELECT cql_valueset_cache_clear()"]);
  });

  it("escapes single quotes in codes", async () => {
    const stmts: string[] = [];
    await seedValuesetCache(
      [{ url: "urn:vs:q", system: "urn:s", code: "o'brien" }],
      async (sql) => {
        stmts.push(sql);
      },
    );
    expect(stmts[2]).toContain("'o''brien'");
  });
});
