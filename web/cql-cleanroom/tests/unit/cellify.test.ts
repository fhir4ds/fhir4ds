import { describe, expect, it } from "vitest";
import { cellify, hasSplittableDefines } from "../../src/lib/cellify";
import { splitCells } from "../../src/lib/cells";

const HDR = "library A version '1.0.0'\nusing FHIR version '4.0.1'\ncontext Patient\n\n";

describe("cellify (S7 auto-cellification)", () => {
  it("inserts named markers before each top-level define", () => {
    const src = HDR + "define A: 1\ndefine B: A + 1\n";
    const out = cellify(src)!;
    expect(out).not.toBeNull();
    const { cells } = splitCells(out);
    expect(cells.map((c) => c.name)).toEqual(["A", "B"]);
    expect(out).toContain("// # %% [name: A]\ndefine A: 1");
  });

  it("handles define function and quoted define names", () => {
    const src = HDR + 'define function F(X Integer): X + 1\ndefine "My Func": F(1)\n';
    const out = cellify(src)!;
    const { cells } = splitCells(out);
    // Quoted space-names get a BARE marker; identity falls to cell-N
    // (client+server DEFINE regexes match marker-safe names only).
    expect(cells).toHaveLength(2);
    expect(cells[0]?.name).toBe("F");
    expect(out).toContain('// # %%\ndefine "My Func":');
  });

  it("does NOT split defines inside block comments", () => {
    const src = HDR + "/*\ndefine Commented: 1\n*/\ndefine Real: 2\n";
    const out = cellify(src)!;
    const { cells } = splitCells(out);
    expect(cells.map((c) => c.name)).toEqual(["Real"]);
    expect(out).not.toContain("[name: Commented]");
  });

  it("does NOT split defines inside string literals", () => {
    const src = HDR + "define S: 'not a define\ndefine T: 2'\ndefine Real: 3\n";
    // The multi-line string is not valid CQL anyway, but the guard must
    // not put a marker inside it.
    const out = cellify(src)!;
    expect(out).not.toMatch(/\[name: T\]/);
  });

  it("does NOT split defines after line comments", () => {
    const src = HDR + "// define NotReal: 0\ndefine Real: 1\n";
    const out = cellify(src)!;
    expect(out).not.toContain("[name: NotReal]");
    expect(out).toContain("[name: Real]");
  });

  it("returns null for already-marked libraries (never duplicates)", () => {
    const marked = HDR + "// # %% [name: A]\ndefine A: 1\n";
    expect(cellify(marked)).toBeNull();
  });

  it("returns null for libraries with no defines", () => {
    expect(cellify("library X version '1.0.0'\n")).toBeNull();
  });

  it("single-define files still cellify (header + 1 cell)", () => {
    const out = cellify(HDR + "define Only: true\n")!;
    expect(splitCells(out).cells.map((c) => c.name)).toEqual(["Only"]);
  });

  it("hasSplittableDefines mirrors cellify candidacy", () => {
    expect(hasSplittableDefines(HDR + "define A: 1\n")).toBe(true);
    expect(hasSplittableDefines("library X version '1'\n")).toBe(false);
    expect(hasSplittableDefines(HDR + "// # %%\ndefine A: 1\n")).toBe(false);
  });

  it("indented define (nested? no — top-level CQL allows leading ws)", () => {
    const out = cellify(HDR + "  define Indented: 1\n")!;
    expect(splitCells(out).cells[0]?.name).toBe("Indented");
  });
});

import { buildCellGraph, dependencyClosure } from "../../src/lib/cell-deps";

describe("S10 quoted-name cells (marker labels with spaces + quoted refs)", () => {
  const HDR2 = "library B version '1.0.0'\nusing FHIR version '4.0.1'\ncontext Patient\n\n";

  it("marker labels may contain spaces and name quoted defines", () => {
    const src2 =
      HDR2 +
      "// # %% [name: Initial Population]\n" +
      'define "Initial Population": true\n';
    const { cells } = splitCells(src2);
    expect(cells.map((c) => c.name)).toEqual(["Initial Population"]);
  });

  it("quoted references count as deps (S10 binder-repro pin)", () => {
    const src2 =
      HDR2 +
      "// # %% [name: Base]\ndefine \"Base\": 1\n" +
      "// # %%\ndefine \"Initial Population\": \"Base\" and true\n";
    const g = buildCellGraph(src2);
    expect(g.refs["Initial Population"]).toContain("Base");
    const closure = dependencyClosure("Initial Population", g.refs, new Set(g.order));
    expect([...closure].sort()).toEqual(["Base", "Initial Population"]);
  });

  it("CMS125-style chain: Numerator closure carries all transitive deps", () => {
    const chain =
      HDR2 +
      "// # %% [name: InAgeRange]\ndefine \"InAgeRange\": true\n" +
      "// # %% [name: PreventiveVisit]\ndefine \"PreventiveVisit\": \"InAgeRange\"\n" +
      "// # %% [name: Initial Population]\ndefine \"Initial Population\": \"InAgeRange\" and \"PreventiveVisit\"\n" +
      "// # %% [name: Numerator]\ndefine \"Numerator\": \"Initial Population\"\n";
    const g = buildCellGraph(chain);
    const closure = dependencyClosure("Numerator", g.refs, new Set(g.order));
    expect([...closure].sort((a, b) => a.localeCompare(b))).toEqual(
      ["Initial Population", "InAgeRange", "Numerator", "PreventiveVisit"].sort((a, b) =>
        a.localeCompare(b),
      ),
    );
  });

  it("plain string literals are NOT deps (quoted-span separation)", () => {
    const src2 =
      HDR2 +
      "// # %% [name: A]\ndefine A: 1\n" +
      "// # %% [name: B]\ndefine B: 'A' = 'A'\n";
    const g = buildCellGraph(src2);
    expect(g.refs["B"]).toEqual([]);
  });
});
