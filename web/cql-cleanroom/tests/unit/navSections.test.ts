import { describe, expect, it } from "vitest";
import {
  expectedItems,
  filterItems,
  libraryItems,
  measureItems,
  parameterItems,
  valuesetItems,
  viewItems,
} from "../../src/lib/navSections";

describe("navSections adapters", () => {
  it("libraryItems carry index + entrypoint badge", () => {
    const items = libraryItems(
      [
        { id: "lib_0", name: "A", text: "library A version '1.0.0'" },
        { id: "lib_1", name: "B", text: "" },
      ],
      "lib_1",
      { lib_0: true },
    );
    expect(items).toHaveLength(2);
    // Name/version default from the CQL header text.
    expect(items[0].label).toBe("A");
    expect(items[0].pill).toBe("1.0.0");
    expect(items[0].sublabel).toBeUndefined();
    expect(items[0].meta?.index).toBe(0);
    expect(items[0].error).toBe(true);
    expect(items[0].entry).toBe(false);
    // No parseable header → fall back to the workspace name, no pill.
    expect(items[1].label).toBe("B");
    expect(items[1].pill).toBeUndefined();
    expect(items[1].entry).toBe(true);
    expect(items[1].id).toBe("library:lib_1");
  });

  it("measureItems fall back to the id and carry the version pill", () => {
    const items = measureItems(
      [
        { id: "msr_0", mainLibraryId: "lib_0", resource: null },
        {
          id: "msr_1",
          mainLibraryId: "lib_1",
          resource: { name: "CMS69", version: "1.0.0" },
        },
      ],
      "msr_1",
    );
    expect(items[0].label).toBe("msr_0");
    expect(items[0].pill).toBeUndefined();
    expect(items[0].sublabel).toBeUndefined();
    expect(items[0].entry).toBe(false);
    expect(items[1].label).toBe("CMS69");
    expect(items[1].pill).toBe("1.0.0");
    expect(items[1].entry).toBe(true);
  });

  it("valuesetItems merge workspace over dataset by url and label sources", () => {
    const items = valuesetItems(
      [{ url: "urn:cleanroom:vs:x1", name: "WS A" }],
      [
        { url: "urn:vs:a", name: "Dataset A", version: "20210220" },
        { url: "urn:cleanroom:vs:x1", name: "shadowed" },
        { url: "urn:vs:b", title: "Titled B", id: "oid-1" },
        { url: "http://cts.example.gov/fhir/ValueSet/seg3" },
        {},
      ],
    );
    expect(items).toHaveLength(5);
    // Workspace copy wins the merge and seeds rename with its raw name.
    expect(items[0].meta?.source).toBe("workspace");
    expect(items[0].label).toBe("WS A");
    expect(items[0].sublabel).toBeUndefined();
    expect(items[0].meta?.name).toBe("WS A");
    // Dataset rows show name + version pill; a workspace url shadows it.
    expect(items[1].meta?.source).toBe("dataset");
    expect(items[1].label).toBe("Dataset A");
    expect(items[1].pill).toBe("20210220");
    // title → id → last url segment fallbacks; no url at all → numbered.
    expect(items[2].label).toBe("Titled B");
    expect(items[2].pill).toBeUndefined();
    expect(items[3].label).toBe("seg3");
    // Numbering counts the DISPLAYED dataset rows (the shadowed one is
    // filtered before the index is taken).
    expect(items[4].label).toBe("dataset valueset 4");
  });

  it("parameterItems flag unbound values", () => {
    const items = parameterItems([
      { name: "P", value: "" },
      { name: "Q", value: "2026" },
    ]);
    expect(items[0].sublabel).toBe("unbound");
    expect(items[1].sublabel).toBe("2026");
  });

  it("expectedItems list ONE item per measure with patient counts", () => {
    const measures = [
      { id: "msr_0", mainLibraryId: "lib_0", resource: { name: "CMS69" } },
      { id: "msr_1", mainLibraryId: "lib_1", resource: null },
    ];
    const items = expectedItems(measures, {
      msr_0: [
        {
          subject: { reference: "Patient/p1" },
          group: [
            {
              population: [
                { code: { coding: [{ code: "initial-population" }] }, count: 1 },
                { code: { coding: [{ code: "numerator" }] }, count: 0 },
              ],
            },
          ],
        },
        { subject: { reference: "Patient/p2" }, group: [] },
        {},
      ],
    });
    // One item per measure — even a measure with NO authored reports
    // lists (empty-but-present), and subject-less reports don't count
    // toward the patient total.
    expect(items).toHaveLength(2);
    expect(items[0].id).toBe("expected:msr_0");
    expect(items[0].label).toBe("CMS69");
    expect(items[0].sublabel).toBe("2 patients");
    expect(items[0].meta?.measureId).toBe("msr_0");
    expect(items[1].label).toBe("msr_1");
    expect(items[1].sublabel).toBe("0 patients");
  });

  it("viewItems fall back to the id when name is empty", () => {
    const items = viewItems([
      { id: "vd_0", name: "", resource: { resource: "MeasureReport" } },
    ]);
    expect(items[0].label).toBe("vd_0");
    expect(items[0].sublabel).toBe("MeasureReport");
  });

  it("filterItems match label, id, and sublabel case-insensitively", () => {
    const items = libraryItems(
      [
        { id: "lib_0", name: "CleanroomDemo", text: "" },
        { id: "lib_1", name: "Helpers", text: "" },
      ],
      null,
    );
    expect(filterItems(items, "clean")).toHaveLength(1);
    expect(filterItems(items, "LIB_1")).toHaveLength(1);
    expect(filterItems(items, "zzz")).toHaveLength(0);
    expect(filterItems(items, "  ")).toHaveLength(2);
  });
});
