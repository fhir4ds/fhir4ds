import { describe, expect, it } from "vitest";
import { zipSync } from "fflate";
import { importMadiePackage } from "../../src/lib/madiePackage";

const enc = (s: string) => new TextEncoder().encode(s);

const MAIN_CQL = `library EXM104 version '8.2.000'
using FHIR version '4.0.1'
include FHIRHelpers version '4.0.1' called FHIRHelpers
valueset "Encounter VS": 'urn:enc'
define "Initial Population":
  true
`;
const DEP_CQL = `library AdultOutpatientEncounters version '2.0.0'
define "Qualifying Encounters": true
`;

const MEASURE = {
  resourceType: "Measure",
  name: "EXM104",
  version: "8.2.000",
  status: "active",
  library: ["http://hl7.org/fhir/us/cqf-measures/Library/EXM104"],
  group: [
    {
      id: "group-1",
      population: [
        {
          code: { coding: [{ system: "http://terminology.hl7.org/CodeSystem/measure-population", code: "initial-population" }] },
          criteria: { language: "text/cql-identifier", expression: "Initial Population" },
        },
      ],
    },
  ],
};

function buildZip(): Uint8Array {
  return zipSync({
    "cql/EXM104-8.2.000.cql": enc(MAIN_CQL),
    "cql/AdultOutpatientEncounters-2.0.0.cql": enc(DEP_CQL),
    "resources/measure-EXM104-8.2.000.json": enc(JSON.stringify(MEASURE, null, 2)),
  });
}

describe("importMadiePackage", () => {
  it("reads cql/ into libraries and resources/ into the Measure", () => {
    const pkg = importMadiePackage(buildZip());
    expect(pkg.libraries.map((l) => l.name).sort()).toEqual([
      "AdultOutpatientEncounters",
      "EXM104",
    ]);
    expect(pkg.measure?.name).toBe("EXM104");
    expect(pkg.primary).toBe("EXM104");
  });

  it("orders tabs main-first per Measure.library[0]", () => {
    const pkg = importMadiePackage(buildZip());
    expect(pkg.libraries[0].name).toBe("EXM104");
  });

  it("backfills libraries from Library resources when cql/ is missing", () => {
    const bytes = zipSync({
      "resources/measure-M-1.json": enc(JSON.stringify(MEASURE)),
      "resources/library-M-1.json": enc(
        JSON.stringify({
          resourceType: "Library",
          name: "M",
          content: [{ contentType: "text/cql", data: "library M version '1'\ndefine \"X\": 1" }],
        }),
      ),
    });
    const pkg = importMadiePackage(bytes);
    expect(pkg.libraries.map((l) => l.name)).toEqual(["M"]);
    expect(pkg.primary).toBe("M");
  });

  it("falls back to cql/ order when Measure.library tail does not match", () => {
    const bytes = zipSync({
      "cql/First-1.cql": enc("library First version '1'\ndefine \"X\": 1"),
      "cql/Second-2.cql": enc("library Second version '2'\ndefine \"Y\": 2"),
      "resources/measure-X-1.json": enc(
        JSON.stringify({ ...MEASURE, library: ["urn:cleanroom:lib:Ghost"] }),
      ),
    });
    const pkg = importMadiePackage(bytes);
    expect(pkg.primary).toBe("First");
    expect(pkg.warnings.some((w) => w.includes("Ghost"))).toBe(true);
  });

  it("warns on files without a library declaration", () => {
    const bytes = zipSync({
      "cql/broken-1.cql": enc("not cql at all"),
    });
    const pkg = importMadiePackage(bytes);
    expect(pkg.libraries).toEqual([]);
    expect(pkg.warnings.some((w) => w.includes("no library declaration"))).toBe(true);
  });

  it("handles a package with no Measure gracefully", () => {
    const bytes = zipSync({ "cql/A-1.cql": enc("library A version '1'\ndefine \"X\": 1") });
    const pkg = importMadiePackage(bytes);
    expect(pkg.measure).toBeNull();
    expect(pkg.primary).toBe("A");
  });
});
