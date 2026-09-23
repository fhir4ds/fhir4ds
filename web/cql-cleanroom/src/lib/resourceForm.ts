/**
 * C3-U1: pure form-state helpers for the Resource Builder.
 *
 * The pane keeps a flat form state ({fieldName: string | string[]}) and
 * converts to/from the FHIR JSON draft. Pure functions only — no React,
 * no worker calls. Discipline (FEATURE_CQL_CLEANROOM_C3.md §3.1):
 *
 * - empty string ⇒ field ABSENT (FHIR absent ≠ ""; INV: preview==payload)
 * - 0..* and 1..* fields render as repeat rows (string[])
 * - choice fields ("value[x]") pick one concrete arm; the JSON key is the
 *   choice name with [x] replaced by the chosen type name (capitalized)
 * - jsonToForm prefills known fields and preserves EVERYTHING it does
 *   not model in a passthrough object (INV-C3-3: no silent data loss;
 *   formToJson merges passthrough back verbatim)
 */

import type { SchemaField } from "./protocol";

/** v1 builder types — exactly the 8 SD-backed types (plan §3.1). */
export const BUILDER_RESOURCE_TYPES = [
  "Patient",
  "Observation",
  "Condition",
  "Encounter",
  "Procedure",
  "MedicationRequest",
  "Immunization",
  "ServiceRequest",
] as const;

export interface FormState {
  resourceType: string;
  values: Record<string, string | string[]>;
  /** choice field name (with [x]) -> chosen concrete type */
  choices: Record<string, string>;
  /** passthrough for unknown/deep fields; merged back verbatim */
  passthrough: Record<string, unknown>;
}

const PRIMITIVES = new Set([
  "string",
  "uri",
  "code",
  "id",
  "boolean",
  "integer",
  "decimal",
  "date",
  "dateTime",
  "instant",
  "time",
  "markdown",
  "canonical",
  "oid",
  "uuid",
  "base64Binary",
  "positiveInt",
  "unsignedInt",
  "xhtml",
]);

/** Fields the schema form renders as inputs (top-level primitives). */
export function editableFields(fields: SchemaField[]): SchemaField[] {
  return fields.filter(
    (f) =>
      f.name !== "resourceType" &&
      f.name !== "id" &&
      !f.name.endsWith("[x]") === false || true,
  );
}

export function isPrimitive(types: string[]): boolean {
  return types.length > 0 && types.every((t) => PRIMITIVES.has(t));
}

export function isRepeatable(cardinality: string): boolean {
  return cardinality.endsWith("*");
}

export function emptyForm(resourceType: string): FormState {
  return { resourceType, values: {}, choices: {}, passthrough: {} };
}

/** Concrete JSON key for a choice field arm: value[x] + Quantity → valueQuantity. */
export function choiceKey(choiceName: string, typeName: string): string {
  return choiceName.replace(/\[x\]$/, capitalize(typeName));
}

function capitalize(s: string): string {
  return s ? s[0].toUpperCase() + s.slice(1) : s;
}

/**
 * Form state → FHIR JSON draft (the exact preview/validate payload).
 * Empty strings are OMITTED; repeat rows drop empty entries; passthrough
 * keys are merged back verbatim (they win conflicts by construction —
 * the pane never renders them).
 */
export function formToJson(
  form: FormState,
  fields: SchemaField[],
): Record<string, unknown> {
  const out: Record<string, unknown> = { resourceType: form.resourceType };
  if (form.values.id !== undefined && form.values.id !== "") {
    out.id = Array.isArray(form.values.id)
      ? form.values.id[0]
      : form.values.id;
  }
  const modeled = new Set<string>(["resourceType", "id"]);
  for (const f of fields) {
    if (f.name === "resourceType" || f.name === "id") {
      continue;
    }
    if (f.choice) {
      modeled.add(f.name);
      const chosen = form.choices[f.name];
      const raw = chosen ? form.values[f.name] : undefined;
      const v = singleValue(raw);
      if (v !== null) out[choiceKey(f.name, chosen!)] = v;
      continue;
    }
    modeled.add(f.name);
    const raw = form.values[f.name];
    if (isRepeatable(f.cardinality)) {
      const rows = Array.isArray(raw)
        ? raw.filter((r) => r !== "")
        : raw !== undefined && raw !== ""
          ? [raw]
          : [];
      // 0..* fields keep ARRAY shape even for a single row (FHIR lists
      // stay lists — the form may add more rows later).
      if (rows.length) out[f.name] = rows.map((r) => coerce(r, f.types));
    } else {
      const v = singleValue(raw);
      if (v !== null) out[f.name] = coerce(v, f.types);
    }
  }
  // Passthrough: unknown fields preserved verbatim (INV-C3-3).
  for (const [k, v] of Object.entries(form.passthrough)) {
    out[k] = v;
  }
  return out;
}

function singleValue(raw: string | string[] | undefined): string | null {
  if (raw === undefined) return null;
  const v = Array.isArray(raw) ? raw[0] : raw;
  return v === undefined || v === "" ? null : v;
}

/** Coerce a string input toward the field's primitive type when unambiguous. */
function coerce(value: string, types: string[]): unknown {
  if (types.includes("boolean")) {
    if (value === "true") return true;
    if (value === "false") return false;
    return value;
  }
  if (types.includes("integer") || types.includes("positiveInt") || types.includes("unsignedInt")) {
    const n = Number.parseInt(value, 10);
    return Number.isNaN(n) ? value : n;
  }
  if (types.includes("decimal")) {
    const n = Number(value);
    return Number.isNaN(n) ? value : n;
  }
  return value;
}

/**
 * FHIR JSON → form state (prefill for editing). Known top-level primitive
 * fields map to inputs; EVERYTHING else lands in passthrough untouched
 * (deep objects, arrays of objects, unknown keys — INV-C3-3).
 */
export function jsonToForm(
  json: Record<string, unknown>,
  fields: SchemaField[],
): FormState {
  const resourceType =
    typeof json.resourceType === "string" ? json.resourceType : "";
  const form = emptyForm(resourceType);
  const byName = new Map(fields.map((f) => [f.name, f]));
  for (const [key, value] of Object.entries(json)) {
    if (key === "resourceType") continue;
    if (key === "id") {
      if (typeof value === "string") form.values.id = value;
      continue;
    }
    // choice arm: valueQuantity → field "value[x]", choice "Quantity"
    const choiceField = fields.find(
      (f) => f.choice && looksLikeChoiceArm(f.name, key),
    );
    if (choiceField && (byName.get(choiceField.name)?.choice ?? false)) {
      const armType = armTypeName(choiceField.name, key);
      if (armType && choiceField.types.includes(armType) && isScalar(value)) {
        form.choices[choiceField.name] = armType;
        form.values[choiceField.name] = value as string;
      } else {
        form.passthrough[key] = value;
      }
      continue;
    }
    const field = byName.get(key);
    if (!field || !isPrimitive(field.types)) {
      form.passthrough[key] = value;
      continue;
    }
    if (isRepeatable(field.cardinality)) {
      if (Array.isArray(value)) {
        form.values[key] = value.map((v) => String(v));
      } else if (isScalar(value)) {
        form.values[key] = [String(value)];
      } else {
        form.passthrough[key] = value;
      }
      continue;
    }
    if (isScalar(value)) {
      form.values[key] = String(value);
    } else {
      form.passthrough[key] = value;
    }
  }
  return form;
}

function isScalar(v: unknown): v is string | number | boolean {
  return (
    typeof v === "string" || typeof v === "number" || typeof v === "boolean"
  );
}

function looksLikeChoiceArm(choiceName: string, key: string): boolean {
  const prefix = choiceName.replace(/\[x\]$/, "");
  return key.length > prefix.length && key.startsWith(prefix);
}

function armTypeName(choiceName: string, key: string): string | null {
  const prefix = choiceName.replace(/\[x\]$/, "");
  const rest = key.slice(prefix.length);
  if (!rest) return null;
  return rest[0].toLowerCase() + rest.slice(1);
}
