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
    expect(items[0].meta?.index).toBe(0);
    expect(items[0].error).toBe(true);
    expect(items[0].entry).toBe(false);
    expect(items[1].entry).toBe(true);
    expect(items[1].id).toBe("library:lib_1");
  });

  it("measureItems label unauthored entries and mark the active one", () => {
    const items = measureItems(
      [
        { id: "msr_0", mainLibraryId: "lib_0", resource: null },
        {
          id: "msr_1",
          mainLibraryId: "lib_1",
          resource: { name: "CMS69" },
        },
      ],
      "msr_1",
    );
    expect(items[0].label).toBe("(unauthored)");
    expect(items[0].entry).toBe(false);
    expect(items[1].label).toBe("CMS69");
    expect(items[1].entry).toBe(true);
  });

  it("valuesetItems merge workspace over dataset by url and label sources", () => {
    const items = valuesetItems(
      [{ url: "urn:vs:a", name: "WS A" }],
      [
        { url: "urn:vs:a", name: "Dataset A" },
        { url: "urn:vs:b", name: "Dataset B" },
      ],
    );
    expect(items).toHaveLength(2);
    expect(items[0].meta?.source).toBe("workspace");
    expect(items[0].label).toBe("WS A");
    expect(items[1].meta?.source).toBe("dataset");
    expect(items[1].label).toBe("Dataset B");
  });

  it("parameterItems flag unbound values", () => {
    const items = parameterItems([
      { name: "P", value: "" },
      { name: "Q", value: "2026" },
    ]);
    expect(items[0].sublabel).toBe("unbound");
    expect(items[1].sublabel).toBe("2026");
  });

  it("expectedItems summarize per-patient population counts", () => {
    const items = expectedItems([
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
    ]);
    expect(items[0].label).toBe("p1");
    expect(items[0].sublabel).toBe("1/2 populations");
    expect(items[1].label).toBe("p2");
    expect(items[1].sublabel).toBe("0/0 populations");
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
