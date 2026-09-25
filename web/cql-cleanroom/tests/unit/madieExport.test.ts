import { describe, expect, it } from "vitest";
import { unzipSync } from "fflate";
import { exportMadiePackage } from "../../src/lib/madieExport";
import { importMadiePackage } from "../../src/lib/madiePackage";

const dec = (b: Uint8Array) => new TextDecoder().decode(b);

const MAIN = `library EXM104 version '8.2.000'
include Dep version '2.0.0'
valueset "Enc": 'urn:enc'
define "Initial Population": true
`;
const DEP = `library Dep version '2.0.0'
valueset "Other": 'urn:other'
define "D": true
`;
const UNRELATED = `library Unused version '1.0.0'
define "U": true
`;

const MEASURE = {
  resourceType: "Measure",
  name: "EXM104",
  version: "8.2.000",
  status: "active",
  library: ["urn:stale"],
  group: [],
};

describe("exportMadiePackage", () => {
  const bytes = exportMadiePackage({
    libraries: [
      { name: "EXM104", text: MAIN },
      { name: "Dep", text: DEP },
      { name: "Unused", text: UNRELATED },
    ],
    primaryName: "EXM104",
    measure: MEASURE,
    valuesets: [
      { resourceType: "ValueSet", id: "enc-1", url: "urn:enc" },
      { resourceType: "ValueSet", id: "unref", url: "urn:unreferenced" },
    ],
  });
  const files = unzipSync(bytes);

  it("writes cql/ for the closure only (unused tab excluded)", () => {
    const keys = Object.keys(files).filter((k) => k.startsWith("cql/"));
    expect(keys.sort()).toEqual([
      "cql/Dep-2.0.0.cql",
      "cql/EXM104-8.2.000.cql",
    ]);
  });

  it("writes library resources for the closure", () => {
    const keys = Object.keys(files).filter((k) => k.includes("library-"));
    expect(keys.some((k) => k.includes("library-EXM104"))).toBe(true);
    expect(keys.some((k) => k.includes("library-Dep"))).toBe(true);
    expect(keys.some((k) => k.includes("library-Unused"))).toBe(false);
    const lib = JSON.parse(dec(files["resources/library-Dep-2.0.0.json"]));
    expect(lib.content[0].contentType).toBe("text/cql");
  });

  it("rewrites Measure.library[] to closure urns, primary first", () => {
    const m = JSON.parse(dec(files["resources/measure-EXM104-8.2.000.json"]));
    expect(m.library).toEqual(["urn:cleanroom:lib:EXM104", "urn:cleanroom:lib:Dep"]);
  });

  it("ships only referenced valuesets", () => {
    expect(Object.keys(files).some((k) => k.includes("valueset-enc"))).toBe(true);
    expect(Object.keys(files).some((k) => k.includes("valueset-unref"))).toBe(false);
  });

  it("round-trips through the importer (main-first, same Measure)", () => {
    const pkg = importMadiePackage(bytes);
    expect(pkg.primary).toBe("EXM104");
    expect(pkg.libraries.map((l) => l.name)).toEqual(["EXM104", "Dep"]);
    expect((pkg.measure?.library as string[] | undefined)?.[0]).toBe("urn:cleanroom:lib:EXM104");
  });
});
