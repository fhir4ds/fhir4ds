/**
 * v2 recursive form model for the Resource Builder
 * (FEATURE_CLEANROOM_TEST_DATA_AUTHORING.md §3.3).
 *
 * The v1 flat {values, choices, passthrough} model only knew top-level
 * primitives; every complex field fell into one global passthrough.
 * v2 drives off resource_schema_tree nodes and models the WHOLE draft
 * as a recursive tree:
 *
 * - primitive leaves: string inputs (absent ≠ "" — INV: preview==payload)
 * - Reference nodes: pickers emitting `{reference: "Type/id"}` OBJECTS,
 *   never scalar strings (F4)
 * - complex types (HumanName, Quantity, …) + backbones: nested sub-forms
 *   from node.children
 * - repeatable nodes (max=*): item lists with a PERSISTENT client _key
 *   per item so passthrough attaches by _key and survives reorder (F2)
 * - depth-cap / hatch / extension / contained / unknown nodes: per-field
 *   JSON hatches — edited as raw JSON, never silently dropped (INV-5)
 * - passthrough exists AT EVERY LEVEL: unknown keys of any object are
 *   preserved verbatim and merged back on emit (round-trip lossless)
 */

import type { SchemaTreeNode } from "./protocol";

/** v1 compat: the builder's SD-backed picker domain. */
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

const PRIMITIVES = new Set([
  "string", "uri", "url", "code", "id", "boolean", "integer", "decimal",
  "date", "dateTime", "instant", "time", "markdown", "canonical", "oid",
  "uuid", "base64Binary", "positiveInt", "unsignedInt", "xhtml",
]);

export function isPrimitiveType(t: string | undefined): boolean {
  return !!t && PRIMITIVES.has(t);
}

export function isRepeatable(cardinality: string | undefined): boolean {
  return !!cardinality && cardinality.endsWith("*");
}

/** Concrete JSON key for a choice arm: value[x] + Quantity → valueQuantity. */
export function choiceKey(choiceName: string, typeName: string): string {
  return choiceName.replace(/\[x\]$/, capitalize(typeName));
}

function capitalize(s: string): string {
  return s ? s[0].toUpperCase() + s.slice(1) : s;
}

let keySeq = 0;
export function newKey(): string {
  keySeq += 1;
  return `k${keySeq}`;
}

/**
 * The recursive form value for ONE field node (or one array item).
 * An ObjectValue carries the modeled children plus a per-level
 * passthrough for keys the tree does not model.
 */
export interface ObjectValue {
  kind: "object";
  /** per-child form values, keyed by the SCHEMA node name */
  children: Record<string, FieldValue>;
  /** unknown JSON keys at this level, preserved verbatim (INV-5) */
  passthrough: Record<string, unknown>;
}

export interface RefValue {
  kind: "ref";
  /** raw reference string "Type/id" — user-typed or picked; may dangle */
  reference: string;
  /** optional display copied through on prefill */
  display?: string;
}

export type FieldValue =
  | { kind: "scalar"; value: string }
  | RefValue
  | ObjectValue
  | { kind: "hatch"; json: string }
  | { kind: "items"; items: Array<{ key: string; value: FieldValue }> };

export interface FormState {
  resourceType: string;
  /** top-level field values keyed by schema node name */
  values: Record<string, FieldValue>;
  /** top-level unknown keys, preserved verbatim */
  passthrough: Record<string, unknown>;
}

export function emptyObject(): ObjectValue {
  return { kind: "object", children: {}, passthrough: {} };
}

export function emptyForm(resourceType: string): FormState {
  return { resourceType, values: {}, passthrough: {} };
}

export function scalarValue(v: FieldValue | undefined): string {
  return v && v.kind === "scalar" ? v.value : "";
}

export function refValue(v: FieldValue | undefined): string {
  return v && v.kind === "ref" ? v.reference : "";
}

/** Default (empty) FieldValue for one schema node. */
export function defaultValueFor(node: SchemaTreeNode): FieldValue {
  if (isRepeatable(node.cardinality)) {
    return { kind: "items", items: [] };
  }
  if (node.hatch) {
    return { kind: "hatch", json: "" };
  }
  if (node.type === "Reference") {
    return { kind: "ref", reference: "" };
  }
  if (isPrimitiveType(node.type)) {
    return { kind: "scalar", value: "" };
  }
  // Complex datatype / backbone with children.
  if ((node.children ?? []).some((c) => c.name === "__hatch__")) {
    return { kind: "hatch", json: "" };
  }
  return emptyObject();
}

/**
 * Coerce a scalar string toward the node's primitive type when
 * unambiguous (booleans, ints, decimals).
 */
export function coerceScalar(value: string, node: SchemaTreeNode): unknown {
  const t = node.type;
  if (t === "boolean") {
    if (value === "true") return true;
    if (value === "false") return false;
    return value;
  }
  if (
    t === "integer" || t === "positiveInt" || t === "unsignedInt" ||
    t === "decimal"
  ) {
    const n = t === "decimal" ? Number(value) : Number.parseInt(value, 10);
    if (value !== "" && !Number.isNaN(n)) return n;
    return value;
  }
  return value;
}

function parseHatch(json: string): unknown | undefined {
  const text = json.trim();
  if (!text) return undefined;
  try {
    return JSON.parse(text);
  } catch {
    return json; // invalid JSON: emit the raw text (validate will reject)
  }
}

function isEmptyEmit(v: unknown): boolean {
  if (v === undefined) return true;
  if (typeof v === "string") return v === "";
  if (v === null) return false; // explicit JSON null is data
  return false;
}

/** Emit ONE node's FieldValue → FHIR JSON value. */
function emitValue(
  node: SchemaTreeNode | undefined,
  value: FieldValue,
): unknown | undefined {
  switch (value.kind) {
    case "scalar": {
      if (value.value === "") return undefined;
      return node ? coerceScalar(value.value, node) : value.value;
    }
    case "ref": {
      if (value.reference === "") return undefined;
      // F4: references are Reference OBJECTS, never scalar strings.
      const out: Record<string, unknown> = { reference: value.reference };
      if (value.display) out.display = value.display;
      return out;
    }
    case "hatch": {
      return parseHatch(value.json);
    }
    case "object": {
      const out = emitObject(node, value);
      return Object.keys(out).length ? out : undefined;
    }
    case "items": {
      const rows = value.items
        .map((it) => emitValue(firstMatchingChild(node), it.value))
        .filter((v) => !isEmptyEmit(v));
      return rows.length ? rows : undefined;
    }
  }
}

function firstMatchingChild(
  node: SchemaTreeNode | undefined,
): SchemaTreeNode | undefined {
  // For items the children describe the item shape; pass the node itself
  // singularized (an array item is never repeatable — no arrays of arrays
  // in FHIR) so item recursion cannot loop.
  if (!node) return node;
  return isRepeatable(node.cardinality)
    ? { ...node, cardinality: "0..1" }
    : node;
}

function emitObject(
  node: SchemaTreeNode | undefined,
  value: ObjectValue,
): Record<string, unknown> {
  const out: Record<string, unknown> = {};
  const byName = new Map((node?.children ?? []).map((c) => [c.name, c]));
  for (const [name, childValue] of Object.entries(value.children)) {
    const childNode = byName.get(name);
    const v = emitValue(childNode, childValue);
    if (!isEmptyEmit(v)) out[name] = v;
  }
  // INV-5: per-level passthrough merged back verbatim (wins by
  // construction — the form never renders those keys).
  for (const [k, v] of Object.entries(value.passthrough)) {
    out[k] = v;
  }
  return out;
}

/** Form state → FHIR JSON draft (the exact preview/validate payload). */
export function formToJson(
  form: FormState,
  root: SchemaTreeNode | null,
): Record<string, unknown> {
  const out = emitObject(root ?? undefined, {
    kind: "object",
    children: form.values,
    passthrough: form.passthrough,
  });
  out.resourceType = form.resourceType;
  return out;
}

function isScalarJson(v: unknown): v is string | number | boolean {
  return (
    typeof v === "string" || typeof v === "number" || typeof v === "boolean"
  );
}

function looksLikeReference(v: unknown): v is Record<string, unknown> {
  return (
    typeof v === "object" && v !== null && !Array.isArray(v) &&
    "reference" in v && typeof (v as Record<string, unknown>).reference === "string"
  );
}

/** Prefill ONE node's value from existing JSON. */
function prefillValue(
  node: SchemaTreeNode | undefined,
  json: unknown,
): FieldValue | undefined {
  if (json === undefined) return undefined;

  if (isRepeatable(node?.cardinality)) {
    const arr = Array.isArray(json) ? json : [json];
    const items = arr
      .map((entry) => prefillValue(firstMatchingChild(node), entry))
      .filter((v): v is FieldValue => v !== undefined)
      .map((v) => ({ key: newKey(), value: v }));
    return { kind: "items", items };
  }

  if (node?.hatch || (node?.children ?? []).some((c) => c.name === "__hatch__")) {
    return { kind: "hatch", json: JSON.stringify(json, null, 2) };
  }

  if (node?.type === "Reference") {
    if (looksLikeReference(json)) {
      const ref = json as { reference?: string; display?: string };
      return {
        kind: "ref",
        reference: typeof ref.reference === "string" ? ref.reference : "",
        display: typeof ref.display === "string" ? ref.display : undefined,
      };
    }
    return { kind: "hatch", json: JSON.stringify(json, null, 2) };
  }

  if (isPrimitiveType(node?.type)) {
    if (isScalarJson(json)) {
      return { kind: "scalar", value: String(json) };
    }
    return { kind: "hatch", json: JSON.stringify(json, null, 2) };
  }

  // Complex object: recurse over children; unknown keys → passthrough.
  if (typeof json === "object" && json !== null && !Array.isArray(json)) {
    const obj = json as Record<string, unknown>;
    const children: Record<string, FieldValue> = {};
    const passthrough: Record<string, unknown> = {};
    const byName = new Map((node?.children ?? []).map((c) => [c.name, c]));
    for (const [k, v] of Object.entries(obj)) {
      const childNode = byName.get(k);
      if (!childNode) {
        passthrough[k] = v;
        continue;
      }
      const fv = prefillValue(childNode, v);
      if (fv !== undefined) children[k] = fv;
    }
    return { kind: "object", children, passthrough };
  }

  // Array where a singleton was expected, or other mismatch: hatch it.
  return { kind: "hatch", json: JSON.stringify(json, null, 2) };
}

/**
 * FHIR JSON → form state (prefill for editing). Modeled keys map to
 * inputs/sub-forms; EVERYTHING the tree does not model lands in
 * passthrough untouched at its own level (INV-5 round-trip).
 */
export function jsonToForm(
  json: Record<string, unknown>,
  root: SchemaTreeNode | null,
): FormState {
  const resourceType =
    typeof json.resourceType === "string" ? json.resourceType : "";
  const form = emptyForm(resourceType);
  const byName = new Map((root?.children ?? []).map((c) => [c.name, c]));
  for (const [k, v] of Object.entries(json)) {
    if (k === "resourceType") continue;
    const node = byName.get(k);
    if (!node) {
      form.passthrough[k] = v;
      continue;
    }
    const fv = prefillValue(node, v);
    if (fv !== undefined) form.values[k] = fv;
  }
  return form;
}

/** v1 compat wrapper used by the dataset edit flow (C3-U3). */
export function prefillBuilder(
  json: Record<string, unknown>,
  root: SchemaTreeNode | null,
): FormState {
  return jsonToForm(json, root);
}
