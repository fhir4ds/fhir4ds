/**
 * Bundle I/O tests (§3.4, F1, S-8): id synthesis from fullUrl, type
 * validation, atomic shape errors, merge last-write-wins, export shape.
 */
import { describe, expect, it } from "vitest";
import {
  BUNDLE_TYPES,
  exportBundle,
  importBundle,
  mergeDatasets,
} from "../../src/lib/bundleIo";

describe("importBundle", () => {
  it("flattens entries and keeps explicit ids", () => {
    const bundle = {
      resourceType: "Bundle",
      type: "collection",
      entry: [
        { resource: { resourceType: "Patient", id: "p1" } },
        { resource: { resourceType: "Observation", id: "o1" } },
      ],
    };
    const res = importBundle(bundle);
    expect(res.resources).toHaveLength(2);
    expect(res.synthesizedIds).toBe(0);
    expect(res.rejected).toEqual([]);
  });

  it("synthesizes ids from urn:uuid fullUrls (F1)", () => {
    const bundle = {
      resourceType: "Bundle",
      type: "transaction",
      entry: [
        {
          fullUrl: "urn:uuid:7f9a4c2e-1234-4abc-9def-000000000001",
          resource: { resourceType: "Patient", gender: "female" },
        },
      ],
    };
    const res = importBundle(bundle);
    expect(res.resources[0].id).toBe(
      "7f9a4c2e-1234-4abc-9def-000000000001",
    );
    expect(res.synthesizedIds).toBe(1);
  });

  it("synthesizes ids from absolute-URL fullUrl tails (F1)", () => {
    const bundle = {
      resourceType: "Bundle",
      type: "searchset",
      entry: [
        {
          fullUrl: "https://example.com/fhir/Patient/p9/_history/2",
          resource: { resourceType: "Patient" },
        },
      ],
    };
    const res = importBundle(bundle);
    expect(res.resources[0].id).toBe("2");
  });

  it("REJECTS entries with no id and no usable fullUrl (counted)", () => {
    const bundle = {
      resourceType: "Bundle",
      type: "collection",
      entry: [
        { resource: { resourceType: "Patient", id: "p1" } },
        { resource: { resourceType: "Observation" } }, // no id, no fullUrl
      ],
    };
    const res = importBundle(bundle);
    expect(res.resources).toHaveLength(1);
    expect(res.rejected).toEqual([1]);
  });

  it("rejects invalid Bundle.type with the allowed set", () => {
    const bundle = { resourceType: "Bundle", type: "nonsense", entry: [] };
    expect(() => importBundle(bundle)).toThrow(/invalid Bundle.type/);
  });

  it("accepts all 9 documented Bundle.type codes", () => {
    for (const t of BUNDLE_TYPES) {
      expect(() =>
        importBundle({ resourceType: "Bundle", type: t, entry: [] }),
      ).not.toThrow();
    }
  });

  it("throws with entry attribution on malformed entries (atomic)", () => {
    const bundle = {
      resourceType: "Bundle",
      type: "collection",
      entry: [
        { resource: { resourceType: "Patient", id: "p1" } },
        "not an object",
      ],
    };
    expect(() => importBundle(bundle)).toThrow(/entry\[1\]/);
  });

  it("throws on missing resourceType / non-Bundle payloads", () => {
    expect(() => importBundle({ resourceType: "Patient" })).toThrow(
      /not a Bundle/,
    );
    expect(() =>
      importBundle({
        resourceType: "Bundle",
        type: "collection",
        entry: [{ resource: { id: "x" } }],
      }),
    ).toThrow(/resourceType/);
  });
});

describe("mergeDatasets (S-8)", () => {
  it("last-write-wins by (resourceType, id)", () => {
    const current = [
      { resourceType: "Patient", id: "p1", gender: "female" },
      { resourceType: "Patient", id: "p2", gender: "male" },
    ];
    const incoming = [
      { resourceType: "Patient", id: "p1", gender: "other" },
      { resourceType: "Observation", id: "o1", status: "final" },
    ];
    const merged = mergeDatasets(current, incoming);
    expect(merged).toHaveLength(3);
    expect(merged[0].gender).toBe("other");
    expect(merged[2].resourceType).toBe("Observation");
  });

  it("id-less resources append without clobbering", () => {
    const current = [{ resourceType: "Patient", id: "p1" }];
    const incoming = [{ resourceType: "Patient", gender: "female" }];
    const merged = mergeDatasets(current, incoming);
    expect(merged).toHaveLength(2);
  });
});

describe("exportBundle", () => {
  it("wraps resources in a collection Bundle", () => {
    const bundle = exportBundle([
      { resourceType: "Patient", id: "p1" },
    ]);
    expect(bundle.resourceType).toBe("Bundle");
    expect(bundle.type).toBe("collection");
    expect(bundle.entry).toEqual([
      { resource: { resourceType: "Patient", id: "p1" } },
    ]);
    expect(importBundle(bundle).resources).toHaveLength(1);
  });
});
