import { describe, expect, it } from "vitest";
import {
  collectValuesetUrls,
  missingValuesetUrls,
  valuesetResourcesOf,
  valuesetWarningMessage,
} from "../../src/lib/valuesetBridge";

/**
 * FHIR4-49 — the loud-fallback guard.
 *
 * `in_valueset` answers from the in-process C++ cache and returns SQL NULL for
 * a ValueSet that was never loaded. Silence there is a wrong answer, so every
 * web app compares the urls its generated SQL asks for against the urls it
 * seeded. These helpers are shared by all apps (web/shared/valuesetBridge.ts),
 * so the extraction contract is pinned here, once.
 */

describe("collectValuesetUrls", () => {
  it("reads the url literal from a translator-emitted in_valueset call", () => {
    const sql =
      `SELECT r.patient_id, r.resource FROM resources r WHERE r.resourceType = 'Condition' ` +
      `AND in_valueset(r.resource, 'code', 'http://cts.nlm.nih.gov/fhir/ValueSet/2.16.840.1.113883.3.464.1003.103.12.1001')`;
    expect(collectValuesetUrls(sql)).toEqual([
      "http://cts.nlm.nih.gov/fhir/ValueSet/2.16.840.1.113883.3.464.1003.103.12.1001",
    ]);
  });

  it("covers the equivalent / fhirpath aliases the translator can emit", () => {
    const sql = [
      "SELECT cql_equivalent_in_valueset(r.resource, 'code', 'http://vs/equivalent')",
      "SELECT fhirpath_in_valueset(r.resource, 'code', 'http://vs/fhirpath')",
      "SELECT fhirpath_equivalent_in_valueset(r.resource, 'code', 'http://vs/fhirpath-equiv')",
    ].join("\n");
    expect(collectValuesetUrls(sql).sort()).toEqual([
      "http://vs/equivalent",
      "http://vs/fhirpath",
      "http://vs/fhirpath-equiv",
    ]);
  });

  it("deduplicates and handles nested calls / escaped quotes", () => {
    const sql =
      `SELECT in_valueset(fhirpath_text(r.resource, 'code'), 'code', 'http://vs/a''b'), ` +
      `in_valueset(r2.resource, 'category', 'http://vs/a''b'), ` +
      `in_valueset(r3.resource, 'type', 'http://vs/other')`;
    expect(collectValuesetUrls(sql).sort()).toEqual([
      "http://vs/a'b",
      "http://vs/other",
    ]);
  });

  it("ignores lookalike identifiers and non-literal urls", () => {
    const sql = [
      "-- my_in_valueset(r, 'code', 'http://vs/comment-only')",
      "SELECT not_in_valueset(r.resource, 'code', 'http://vs/lookalike')",
      "SELECT xin_valueset(r.resource, 'code', 'http://vs/prefixed')",
      "SELECT in_valueset(r.resource, 'code', 'http://vs/' || r.vs)",
      "SELECT in_valueset(r.resource)",
    ].join("\n");
    expect(collectValuesetUrls(sql)).toEqual([]);
  });

  it("returns nothing for empty or unrelated SQL", () => {
    expect(collectValuesetUrls("")).toEqual([]);
    expect(collectValuesetUrls("SELECT 1")).toEqual([]);
  });
});

describe("missingValuesetUrls", () => {
  const sql = "SELECT in_valueset(r.resource, 'code', 'http://vs/loaded'), in_valueset(r.resource, 'code', 'http://vs/missing')";

  it("reports only the urls the cache does not hold", () => {
    expect(missingValuesetUrls(sql, ["http://vs/loaded"])).toEqual([
      "http://vs/missing",
    ]);
  });

  it("is empty when everything is seeded (no false alarm)", () => {
    expect(
      missingValuesetUrls(sql, ["http://vs/loaded", "http://vs/missing"]),
    ).toEqual([]);
    expect(missingValuesetUrls("SELECT 1", [])).toEqual([]);
  });

  it("accepts any iterable of loaded urls", () => {
    expect(missingValuesetUrls(sql, new Set(["http://vs/loaded"]))).toEqual([
      "http://vs/missing",
    ]);
  });
});

describe("valuesetResourcesOf", () => {
  it("keeps only FHIR ValueSet resources", () => {
    const resources = [
      { resourceType: "Patient", id: "p1" },
      { resourceType: "ValueSet", id: "vs1", url: "http://vs/1" },
      { resourceType: "Condition", id: "c1" },
      { resourceType: "ValueSet", id: "vs2", url: "http://vs/2" },
    ];
    expect(valuesetResourcesOf(resources).map((r) => r.id)).toEqual([
      "vs1",
      "vs2",
    ]);
  });
});

describe("valuesetWarningMessage", () => {
  it("names every unloaded url and explains the empty-population risk", () => {
    const msg = valuesetWarningMessage(["http://vs/missing"]);
    expect(msg).toContain("http://vs/missing");
    expect(msg).toContain("not loaded");
    expect(msg).toContain("UNKNOWN");
    expect(msg).toContain("empty");
  });

  it("is empty when nothing is missing", () => {
    expect(valuesetWarningMessage([])).toBe("");
  });
});
