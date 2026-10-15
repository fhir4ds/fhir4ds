/** S1R Muse MF1/MF3: scanner + resolution unit tests (vitest). */
import { describe, expect, it } from "vitest";
import { declaredValuesetUrls } from "../../src/lib/terminologyRuntime";

describe("declaredValuesetUrls", () => {
  it("matches quoted name + quoted url", () => {
    const text = `library T\nvalueset "BP": 'http://cts.nlm.nih.gov/fhir/ValueSet/1.2.3'`;
    expect(declaredValuesetUrls(text)).toEqual([
      "http://cts.nlm.nih.gov/fhir/ValueSet/1.2.3",
    ]);
  });
  it("matches bare name + trailing punctuation", () => {
    const text = `library T\nvalueset BP: http://example.org/vs/4,`;
    expect(declaredValuesetUrls(text)).toEqual(["http://example.org/vs/4"]);
  });
  it("matches urn: valuesets", () => {
    const text = `library T\nvalueset "X": urn:oid:1.2.3.4`;
    expect(declaredValuesetUrls(text)).toEqual(["urn:oid:1.2.3.4"]);
  });
  it("skips non-url values (inline codes, identifiers)", () => {
    const text = `library T\nvalueset "Y": 'not-a-url'\ndefine D: 1`;
    expect(declaredValuesetUrls(text)).toEqual([]);
  });
  it("finds multiple declarations across lines", () => {
    const text = [
      "library T",
      'valueset "A": http://a.example/VS/1',
      'valueset "B": http://b.example/VS/2',
    ].join("\n");
    expect(declaredValuesetUrls(text).sort()).toEqual([
      "http://a.example/VS/1",
      "http://b.example/VS/2",
    ]);
  });
});
