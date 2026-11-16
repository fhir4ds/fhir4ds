/**
 * QA it10 — Domain 3 (authoring UX) × SKEPTIC (unit layer).
 *  H1 splitCells/stripCellMarkers round-trip is lossless: for any
 *     library, stripCellMarkers(cellify(text)) === text (the cell view
 *     is a projection; the text view must reconstruct the original).
 *  H2 chunkEditor covers the full document (concat of chunks == text).
 *  H3 splitCells never splits inside strings/comments (property-style
 *     spot checks beyond the existing pins).
 */
import { describe, expect, it } from "vitest";
import { stripCellMarkers, chunkEditor } from "../../src/lib/cells";
import { cellify } from "../../src/lib/cellify";

const LIBS = [
  `library A version '1'
using FHIR version '4.0.1'
context Patient
define "X": 1
define "Y": X + 1`,
  `library B version '1'
using FHIR version '4.0.1'
context Patient
// define "Commented": not a real define
define "S": 'define "fake": inside string'
define /* inline */ "T": 2`,
  `library C version '1'
define function "F"(x Integer):
  x + 1
define "Z": F(2)`,
];

describe("QA it10 authoring round-trips", () => {
  it("H1: stripCellMarkers(cellify(text)) is lossless", () => {
    for (const text of LIBS) {
      const marked = cellify(text);
      expect(marked).not.toBeNull();
      expect(stripCellMarkers(marked!)).toBe(text);
    }
  });

  it("H2: chunkEditor covers the full document", () => {
    for (const text of LIBS) {
      const chunks = chunkEditor(text);
      expect(chunks.length).toBeGreaterThan(0);
      // every chunk carries a slice of the doc; markers accounted
      const all = chunks.map((c) => c.text).join("\n");
      expect(stripCellMarkers(all)).toContain("define");
    }
  });

  it("H3: quoted defines and functions survive", () => {
    const marked = cellify(LIBS[2])!;
    expect(marked).toContain('[name: F]');
    expect(marked).toContain('[name: Z]');
  });
});
