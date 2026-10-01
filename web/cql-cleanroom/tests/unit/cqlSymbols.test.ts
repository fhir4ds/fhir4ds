import { describe, expect, it } from "vitest";
import { countReferences, extractCqlSymbols } from "../../src/lib/cqlSymbols";

describe("extractCqlSymbols", () => {
  it("extracts a CMS69-style declaration surface", () => {
    const text = [
      "library CMS69 version '1.0.0'",
      "using FHIR version '4.0.1'",
      "include FHIRHelpers version '4.0.1' called FHIRHelpers",
      'include "Hospice" version \'1.0.0\'',
      'valueset "Hospice": \'urn:vs:hospice\'',
      'parameter "Measurement Period" Interval<DateTime>',
      'codesystem "LOINC": \'http://loinc.org\'',
      'code "Tobacco Status": \'72166-2\' from "LOINC"',
      "context Patient",
      'define "Initial Population":',
      "  true",
      'define function "Age at Start"(pt):',
      "  1",
    ].join("\n");
    const s = extractCqlSymbols(text);
    expect(s.defines).toEqual([
      { name: "Initial Population", line: 10 },
    ]);
    expect(s.functions).toEqual([{ name: "Age at Start", line: 12 }]);
    expect(s.parameters).toEqual([{ name: "Measurement Period", line: 6 }]);
    expect(s.valuesets).toEqual([{ name: "Hospice", line: 5 }]);
    expect(s.codesystems).toEqual([{ name: "LOINC", line: 7 }]);
    expect(s.codeDecls).toEqual([{ name: "Tobacco Status", line: 8 }]);
    expect(s.includes).toEqual([
      { name: "FHIRHelpers", alias: "FHIRHelpers", line: 3 },
      { name: "Hospice", alias: "Hospice", line: 4 },
    ]);
  });

  it("handles bare names and dedupes repeats", () => {
    const s = extractCqlSymbols(
      "define Foo:\n  1\n\ndefine Foo:\n  2\n\nparameter MP System.DateTime",
    );
    expect(s.defines).toEqual([{ name: "Foo", line: 1 }]);
    expect(s.parameters).toEqual([{ name: "MP", line: 7 }]);
  });

  it("does not treat body lines or comments as declarations", () => {
    const s = extractCqlSymbols(
      'define "A":\n  // define "Fake":\n  exists([Patient] P where P.code = "B")',
    );
    expect(s.defines).toEqual([{ name: "A", line: 1 }]);
  });
});

describe("countReferences", () => {
  it("counts body references, skipping the declaration line", () => {
    const text = [
      'define "A":',
      '  exists "B"',
      'define "B":',
      '  "A" and "A" or exists "A"',
    ].join("\n");
    expect(countReferences(text, "A", 1)).toBe(3);
    expect(countReferences(text, "B", 3)).toBe(1);
  });

  it("does not match partial identifiers", () => {
    const text = 'define "Age":\n  "Ages" and "Age"';
    expect(countReferences(text, "Age", 1)).toBe(1);
  });
});
