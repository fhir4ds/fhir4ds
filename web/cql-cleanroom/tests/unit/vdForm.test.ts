/**
 * VD form-model tests (FEATURE_VD_FORM_EDITOR §3.1): structural block
 * reasons (§2.2), round-trip losslessness on the modeled subset incl.
 * explicit-false collection + description/tag passthrough (§2.3/§2.4),
 * named loss paths (Muse #5), preserved-note inputs (§2.3.1).
 */
import { describe, expect, it } from "vitest";
import {
  isValidSqlName,
  jsonToVdForm,
  vdFormBlockedReasons,
  vdFormPreservedNotes,
  vdFormRoundTripLosses,
  vdFormToJson,
} from "../../src/lib/vdForm";

const simpleVd = {
  resource: "Patient",
  name: "patients",
  status: "draft",
  select: [
    {
      column: [
        { name: "id", path: "id", type: "string" },
        { name: "birthDate", path: "birthDate", type: "date" },
        {
          name: "given",
          path: "name.given",
          type: "string",
          collection: true,
          description: "given names",
          tag: [{ name: "core", value: "true" }],
        },
      ],
    },
  ],
};

describe("sql-name", () => {
  it("accepts letter-first alnum_underscore and rejects the rest", () => {
    expect(isValidSqlName("patients")).toBe(true);
    expect(isValidSqlName("col_2")).toBe(true);
    expect(isValidSqlName("2col")).toBe(false);
    expect(isValidSqlName("col-x")).toBe(false);
    expect(isValidSqlName("")).toBe(false);
  });
});

describe("vdFormBlockedReasons (structural, §2.2)", () => {
  it("passes single-select tabular VDs", () => {
    expect(vdFormBlockedReasons(simpleVd)).toEqual([]);
  });

  it("passes single-select with forEach (passthrough + scope pill)", () => {
    const vd = {
      ...simpleVd,
      select: [{ forEach: "contact", column: [{ name: "id", path: "%resource.id" }] }],
    };
    expect(vdFormBlockedReasons(vd)).toEqual([]);
  });

  it("blocks multi-select with a plain-language reason", () => {
    const vd = {
      resource: "Patient",
      select: [
        { column: [{ name: "a", path: "id" }] },
        { column: [{ name: "b", path: "id" }] },
      ],
    };
    const r = vdFormBlockedReasons(vd);
    expect(r).toHaveLength(1);
    expect(r[0]).toMatch(/multi-select/i);
  });

  it("blocks nested select, unionAll, repeat, and joins", () => {
    const nested = {
      resource: "Patient",
      select: [{ select: [{ column: [{ name: "a", path: "id" }] }] }],
    };
    expect(vdFormBlockedReasons(nested)[0]).toMatch(/nested selects/i);
    const union = {
      resource: "Patient",
      select: [
        { column: [{ name: "a", path: "id" }], unionAll: [{ column: [{ name: "b", path: "id" }] }] },
      ],
    };
    expect(vdFormBlockedReasons(union)[0]).toMatch(/unionAll/i);
    const repeat = {
      resource: "Questionnaire",
      select: [{ repeat: ["item"], column: [{ name: "a", path: "id" }] }],
    };
    expect(vdFormBlockedReasons(repeat)[0]).toMatch(/repeat/i);
    const joined = {
      resource: "Patient",
      select: [{ column: [{ name: "a", path: "id" }] }],
      joins: [{ name: "enc", resource: "Encounter" }],
    };
    expect(vdFormBlockedReasons(joined)[0]).toMatch(/joins/i);
  });

  it("blocks a VD with no select structure", () => {
    expect(vdFormBlockedReasons({ resource: "Patient" })[0]).toMatch(/no select/i);
  });
});

describe("round-trip losslessness (§2.3/§2.4)", () => {
  it("is lossless on the modeled subset incl. extras passthrough", () => {
    expect(vdFormRoundTripLosses(simpleVd)).toEqual([]);
  });

  it("preserves explicit collection:false verbatim (tri-state state)", () => {
    const vd = {
      resource: "Patient",
      select: [
        { column: [{ name: "id", path: "id", collection: false }] },
      ],
    };
    expect(vdFormRoundTripLosses(vd)).toEqual([]);
    const round = vdFormToJson(jsonToVdForm(vd));
    const col = (round.select as Array<{ column: Array<{ collection: unknown }> }>)[0].column[0];
    expect(col.collection).toBe(false);
  });

  it("preserves a column with name but no path (empty-string omission)", () => {
    const vd = {
      resource: "Patient",
      select: [{ column: [{ name: "half" }] }],
    };
    expect(vdFormRoundTripLosses(vd)).toEqual([]);
  });

  it("preserves forEach/where/constants/unknown top-level keys verbatim", () => {
    const vd = {
      resourceType: "ViewDefinition",
      id: "vd-1",
      name: "contacts",
      title: "Contacts",
      profile: ["http://example.org/profile"],
      fhirVersion: ["4.0.1"],
      select: [
        {
          forEach: "contact",
          where: [{ path: "system", equals: "phone" }],
          column: [{ name: "system", path: "system" }],
        },
      ],
      where: [{ path: "active", equals: "true" }],
      constants: [{ name: "loinc", valueCode: "8480-6" }],
      publisher: "fhir4ds",
    };
    expect(vdFormRoundTripLosses(vd)).toEqual([]);
    const round = vdFormToJson(jsonToVdForm(vd));
    expect(round.title).toBe("Contacts");
    expect(round.publisher).toBe("fhir4ds");
    expect((round.constants as unknown[]).length).toBe(1);
  });

  it("drops fully-empty rows but keeps half-typed ones (§2.4)", () => {
    const vd = {
      resource: "Patient",
      select: [{ column: [{ name: "", path: "" }] }],
    };
    // An all-empty row is DROPPED on emit — that is a loss by design
    // (half-typed drafts); the guard must report it so the flip blocks.
    const losses = vdFormRoundTripLosses(vd);
    expect(losses.length).toBeGreaterThan(0);
  });

  it("reports a NAMED column path when a non-object column entry appears", () => {
    const vd = {
      resource: "Patient",
      select: [{ column: [{ name: "ok", path: "id" }, "junk" as unknown] }],
    };
    const losses = vdFormRoundTripLosses(vd);
    expect(losses).toHaveLength(1);
    expect(losses[0]).toMatch(/column \(index 1\)/);
  });

  it("names an existing column in the loss path (Muse #5)", () => {
    const vd = {
      resource: "Patient",
      select: [
        {
          column: [
            { name: "id", path: "id" },
            { name: "status", path: "status", type: "code" },
          ],
        },
      ],
    };
    // Simulate an unrepresentable column value: a non-string type entry.
    const bad = structuredClone(vd);
    (bad.select[0].column as Array<Record<string, unknown>>)[1].type = 42;
    const losses = vdFormRoundTripLosses(bad);
    expect(losses).toHaveLength(1);
    expect(losses[0]).toMatch(/column 'status' \(index 1\)/);
  });
});

describe("emit order (§2.3 human FHIR order)", () => {
  it("emits resourceType/id/name/status/resource before passthrough and select", () => {
    const vd = {
      publisher: "fhir4ds",
      resource: "Patient",
      status: "draft",
      name: "patients",
      id: "vd-1",
      resourceType: "ViewDefinition",
      select: [{ column: [{ name: "id", path: "id" }] }],
    };
    const round = vdFormToJson(jsonToVdForm(vd));
    expect(Object.keys(round)).toEqual([
      "resourceType",
      "id",
      "name",
      "status",
      "resource",
      "publisher",
      "select",
    ]);
  });
});

describe("preserved-notes inputs (§2.3.1)", () => {
  it("derives the forEach scope expression and filter/constant counts", () => {
    const notes = vdFormPreservedNotes({
      resource: "Patient",
      select: [{ forEach: "contact", where: [{ path: "a", equals: "b" }], column: [] }],
      where: [{ path: "c", equals: "d" }],
      constants: [{ name: "k", valueString: "v" }],
    });
    expect(notes.scopeExpr).toBe("contact");
    expect(notes.filters).toBe(2);
    expect(notes.constants).toBe(1);
  });

  it("returns null scope for tabular VDs", () => {
    expect(vdFormPreservedNotes(simpleVd).scopeExpr).toBeNull();
  });
});
