import { describe, expect, it } from "vitest";
import {
  appendDefine,
  defineBody,
  parseAtom,
  parseConjunction,
  parseDefine,
  serializeAtom,
  serializeBody,
  spliceDefine,
} from "../../src/lib/cqlBuilder";

const DEMO = [
  "library CleanroomDemo version '1.0.0'",
  "using FHIR version '4.0.1'",
  "include FHIRHelpers version '4.0.1' called FHIRHelpers",
  "",
  'define "Initial Population":',
  "  exists([Patient] P where P.gender = 'female')",
  "",
  'define "Has Name":',
  "  exists([Patient] P where P.name.first().given.first() is not null)",
  "",
  'valueset "Hospice": \'urn:vs:hospice\'',
  'define "Hospice During":',
  "  exists([Condition: \"Hospice\"] C where C.onset during \"Measurement Period\")",
].join("\n");

describe("parseDefine", () => {
  it("parses the demo population shape into structured atoms", () => {
    const e = parseDefine(DEMO, "Initial Population");
    expect(e).toEqual({
      name: "Initial Population",
      kind: "exists",
      retrieve: { resourceType: "Patient", alias: "P", valueset: undefined },
      where: [
        {
          type: "compare",
          path: "P.gender",
          op: "=",
          literal: { kind: "string", value: "female" },
        },
      ],
      raw: "exists([Patient] P where P.gender = 'female')",
    });
  });

  it("round-trips a supported body byte-for-byte", () => {
    const e = parseDefine(DEMO, "Initial Population");
    expect(serializeBody(e!)).toBe(e!.raw);
  });

  it("degrades function-call conjuncts to verbatim custom atoms", () => {
    const e = parseDefine(DEMO, "Has Name");
    expect(e!.kind).toBe("exists");
    expect(e!.retrieve).toEqual({
      resourceType: "Patient",
      alias: "P",
      valueset: undefined,
    });
    expect(e!.where).toEqual([
      { type: "custom", text: "P.name.first().given.first() is not null" },
    ]);
    expect(serializeBody(e!)).toBe(e!.raw);
  });

  it("parses valueset-qualified retrieves and valueset membership", () => {
    const e = parseDefine(DEMO, "Hospice During");
    expect(e!.retrieve).toEqual({
      resourceType: "Condition",
      alias: "C",
      valueset: "Hospice",
    });
    // `onset during "Measurement Period"` is outside the atom grammar.
    expect(e!.where).toEqual([
      {
        type: "custom",
        text: 'C.onset during "Measurement Period"',
      },
    ]);
    expect(serializeBody(e!)).toBe(e!.raw);
  });

  it("returns kind custom for bodies outside the grammar", () => {
    const lib = `${DEMO}\n\ndefine "Intervals":\n  [Encounter] E\n    where E.period overlaps Interval[@2024-01-01, @2024-12-31]\n`;
    const e = parseDefine(lib, "Intervals");
    // Still a retrieve+where — but the multiline where has an interval
    // literal, which no atom matches; custom atom keeps it verbatim.
    expect(e!.kind).toBe("list");
    expect(e!.where).toHaveLength(1);
    expect(e!.where[0].type).toBe("custom");
    // Statement layout canonicalizes to one line; the logic text is
    // verbatim.
    expect(serializeBody(e!)).toBe(e!.raw.replace(/\s+/g, " "));
  });

  it("keeps a genuinely arbitrary body verbatim as raw", () => {
    const lib = `${DEMO}\n\ndefine "Age Filter":\n  AgeInYearsAt(start of "Measurement Period") >= 18\n`;
    const e = parseDefine(lib, "Age Filter");
    expect(e!.kind).toBe("custom");
    expect(e!.raw).toBe("AgeInYearsAt(start of \"Measurement Period\") >= 18");
  });

  it("returns null for an unknown define", () => {
    expect(parseDefine(DEMO, "Nope")).toBeNull();
  });
});

describe("atom/conjunction parsing", () => {
  it("classifies literal kinds", () => {
    expect(parseAtom("P.age >= 18")).toEqual({
      type: "compare",
      path: "P.age",
      op: ">=",
      literal: { kind: "number", value: "18" },
    });
    expect(parseAtom("P.active = true")).toEqual({
      type: "compare",
      path: "P.active",
      op: "=",
      literal: { kind: "boolean", value: "true" },
    });
    expect(parseAtom("E.period >= @2024-01-01")).toEqual({
      type: "compare",
      path: "E.period",
      op: ">=",
      literal: { kind: "datetime", value: "@2024-01-01" },
    });
    expect(parseAtom('C.code in "Hospice"')).toEqual({
      type: "valueset",
      path: "C.code",
      valueset: "Hospice",
    });
  });

  it("splits and-joined conjuncts", () => {
    const atoms = parseConjunction("P.gender = 'female' and P.active = true");
    expect(atoms).toHaveLength(2);
    expect(atoms.every((a) => a.type === "compare")).toBe(true);
  });

  it("keeps an or/nested group as a text predicate beside parsed conjuncts", () => {
    const atoms = parseConjunction("(P.gender = 'female' or P.age > 65) and P.active = true");
    expect(atoms).toHaveLength(2);
    expect(atoms[0].type).toBe("custom");
    expect(atoms[1]).toMatchObject({ type: "compare", path: "P.active" });
    // The round-trip stays byte-exact.
    expect(atoms.map(serializeAtom).join(" and ")).toBe(
      "(P.gender = 'female' or P.age > 65) and P.active = true",
    );
  });
});

describe("spliceDefine / appendDefine", () => {
  it("replaces one statement block, neighbors untouched", () => {
    const next = spliceDefine(DEMO, "Has Name", 'define "Has Name":\n  exists([Patient] P where P.name exists)');
    expect(next).toContain("define \"Initial Population\":\n  exists([Patient] P where P.gender = 'female')");
    expect(next).toContain('define "Has Name":\n  exists([Patient] P where P.name exists)');
    expect(next).toContain('valueset "Hospice"');
    expect(next).toContain('"Hospice During"');
    expect(parseDefine(next, "Has Name")!.raw).toBe(
      "exists([Patient] P where P.name exists)",
    );
  });

  it("appends a new define at the end", () => {
    const next = appendDefine(DEMO, 'define "Builder Check":\n  true');
    expect(defineBody(next, 0)).not.toContain("Builder Check");
    expect(parseDefine(next, "Builder Check")!.kind).toBe("custom");
    expect(next.trimEnd().endsWith('define "Builder Check":\n  true')).toBe(true);
  });
});
