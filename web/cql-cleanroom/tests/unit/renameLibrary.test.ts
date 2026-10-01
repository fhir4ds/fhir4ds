import { describe, expect, it } from "vitest";
import {
  isValidLibraryName,
  renameLibrary,
} from "../../src/lib/renameLibrary";
import { closeTab, neighborTabId, openTab, parseTabId, tabId } from "../../src/lib/editorTabs";

describe("renameLibrary", () => {
  const libs = [
    {
      id: "lib_0",
      name: "Main",
      text: "library Main version '1.0.0'\n\nusing FHIR",
    },
    {
      id: "lib_1",
      name: "Helpers",
      text: "library Helpers\n\ninclude Main version '1.0.0' called M\ninclude MainOnlyNotThis",
    },
  ];

  it("rewrites the header and sibling includes", () => {
    const next = renameLibrary(libs, "lib_0", "Renamed");
    expect(next).not.toBeNull();
    expect(next![0].text).toContain("library Renamed version '1.0.0'");
    expect(next![0].text).not.toContain("library Main");
    expect(next![1].text).toContain("include Renamed version '1.0.0' called M");
    // Unrelated identifiers (MainOnlyNotThis) survive.
    expect(next![1].text).toContain("include MainOnlyNotThis");
    expect(next![1].text).not.toContain("include Main version");
  });

  it("updates the name mirror and leaves other libraries' names", () => {
    const next = renameLibrary(libs, "lib_0", "Renamed")!;
    expect(next[0].name).toBe("Renamed");
    expect(next[1].name).toBe("Helpers");
  });

  it("rejects invalid identifiers and unknown ids", () => {
    expect(isValidLibraryName("Good_Name2")).toBe(true);
    expect(isValidLibraryName("2bad")).toBe(false);
    expect(isValidLibraryName("has space")).toBe(false);
    expect(isValidLibraryName("")).toBe(false);
    expect(renameLibrary(libs, "lib_0", "2bad")).toBeNull();
    expect(renameLibrary(libs, "lib_x", "Fine")).toBeNull();
  });

  it("is a no-op when the name is unchanged", () => {
    expect(renameLibrary(libs, "lib_0", "Main")).toBe(libs);
  });
});

describe("editorTabs", () => {
  it("tabId/parseTabId round-trip", () => {
    const id = tabId("library", "lib_0");
    expect(id).toBe("library:lib_0");
    expect(parseTabId(id)).toEqual({ kind: "library", resourceId: "lib_0" });
  });

  it("openTab focuses existing and appends new", () => {
    const t = { id: tabId("library", "lib_0"), kind: "library" as const, resourceId: "lib_0" };
    expect(openTab([t], { ...t, id: tabId("library", "lib_0") })).toHaveLength(1);
    expect(openTab([t], { id: "measure:msr_0", kind: "measure", resourceId: "msr_0" })).toHaveLength(2);
  });

  it("closeTab + neighborTabId pick the right successor", () => {
    const tabs = [
      { id: "library:lib_0" as const, kind: "library" as const, resourceId: "lib_0" },
      { id: "measure:msr_0" as const, kind: "measure" as const, resourceId: "msr_0" },
      { id: "view:vd_0" as const, kind: "view" as const, resourceId: "vd_0" },
    ];
    expect(neighborTabId(tabs, "measure:msr_0")).toBe("view:vd_0");
    expect(neighborTabId(tabs, "view:vd_0")).toBe("measure:msr_0");
    expect(closeTab(tabs, "measure:msr_0")).toHaveLength(2);
    expect(neighborTabId(tabs, "library:zzz")).toBeNull();
  });
});
