import { useEffect, useMemo, useRef, useState } from "react";
import type { DatasetInfo, Diagnostic, Transport, SchemaTreeNode } from "./transport";

/** A node from GET /api/schema-tree (subset of fields the form needs). */
export type SchemaNode = SchemaTreeNode;

interface Props {
  transport: Transport;
  datasets: string[];
  dataHint: string | null;
  /** Prefill the builder from the DatasetPane 'Edit in builder' action. */
  initialResource?: Record<string, unknown> | null;
  /** Preselect the target dataset file (e.g. the file the resource came from). */
  initialDatasetPath?: string | null;
}

/** Starter templates: common authoring cases (conductor addition to v4.1). */
const TEMPLATES: Record<string, unknown> = {
  Patient: {
    resourceType: "Patient",
    id: "example",
    gender: "male",
    birthDate: "1974-12-25",
    name: [{ family: "Chalmers", given: ["John"] }],
  },
  Observation: {
    resourceType: "Observation",
    id: "example-obs",
    status: "final",
    code: {
      coding: [{ system: "http://loinc.org", code: "8480-6", display: "BP" }],
    },
    subject: { reference: "Patient/example" },
    effectiveDateTime: "2024-01-01",
    valueQuantity: { value: 120, unit: "mmHg" },
  },
  Condition: {
    resourceType: "Condition",
    id: "example-cond",
    clinicalStatus: {
      coding: [{ system: "http://terminology.hl7.org/CodeSystem/condition-clinical", code: "active" }],
    },
    code: { text: "Example condition" },
    subject: { reference: "Patient/example" },
  },
  MedicationRequest: {
    resourceType: "MedicationRequest",
    id: "example-med",
    status: "active",
    intent: "order",
    medicationCodeableConcept: { text: "Example medication" },
    subject: { reference: "Patient/example" },
  },
};

/** Curated common-type list for the picker (schema tree serves the rest). */
const COMMON_TYPES = [
  "Account", "AllergyIntolerance", "Appointment", "CarePlan", "CareTeam",
  "Claim", "Condition", "Coverage", "Device", "DiagnosticReport",
  "DocumentReference", "Encounter", "Goal", "Immunization", "Location",
  "Measure", "MeasureReport", "Medication", "MedicationRequest",
  "MedicationStatement", "Observation", "Organization", "Patient",
  "Practitioner", "PractitionerRole", "Procedure", "Questionnaire",
  "QuestionnaireResponse", "RelatedPerson", "ResearchStudy", "Schedule",
  "ServiceRequest", "Specimen", "ValueSet",
];

type Row = { path: string; value: string; node?: SchemaNode };

/** Candidate target for a Reference picker: type + id from the loaded dataset files. */
type RefCandidate = { type: string; id: string };

/**
 * Curated bindings for common bound code fields. The schema tree exposes no
 * binding/valueSet metadata, so these dropdowns come from this client-side
 * map (documented limitation) — unbound codes fall back to free text.
 * Keyed by field leaf; inner key is a context (parent segment or resourceType).
 */
const CURATED_BINDINGS: Record<string, Record<string, string[]>> = {
  gender: { "": ["male", "female", "other", "unknown"] },
  use: { name: ["usual", "official", "temp", "nickname", "anonymous", "old", "maiden"] },
  system: { telecom: ["phone", "fax", "email", "pager", "url", "sms", "other"] },
  status: { Observation: ["registered", "preliminary", "final", "amended", "entered-in-error", "unknown"] },
  active: { "": ["true", "false"] },
};

function curatedOptions(leaf: string, context: string): string[] | null {
  const m = CURATED_BINDINGS[leaf];
  if (!m) return null;
  if (m[context]) return m[context];
  if (context && m[""]) return m[""];
  return null;
}

/** Collect all schema arms carrying the given choice_group marker (recursive). */
function scanChoiceArms(node: SchemaNode | null, group: string): SchemaNode[] {
  if (!node) return [];
  const out: SchemaNode[] = [];
  const walk = (n: SchemaNode) => {
    for (const c of n.children ?? []) {
      if (c.hatch) continue;
      if (c.choice_group === group) {
        // Dedupe by arm name — the recursive scan can reach the same arm
        // through nested subtrees (extension value[x] mirrors root value[x]).
        if (!out.some((x) => x.name === c.name)) out.push(c);
      } else if ((c.children?.length ?? 0) > 0) walk(c);
    }
  };
  walk(node);
  return out;
}

/** Typed widget for a primitive field, dispatched on the schema node type. */
function PrimitiveInput({
  path,
  value,
  node,
  resourceType,
  onChange,
}: {
  path: string;
  value: string;
  node: SchemaNode;
  resourceType: string;
  onChange: (raw: string) => void;
}) {
  const t = node.type;
  if (t === "boolean") {
    return (
      <input
        type="checkbox"
        className="dev-rbcheck"
        checked={value === "true"}
        onChange={(e) => onChange(e.target.checked ? "true" : "false")}
      />
    );
  }
  if (t === "date" || t === "dateTime") {
    // v1: the date picker writes the date part; time components stay JSON-editable.
    const datePart = (typeof value === "string" ? value : "").slice(0, 10);
    return (
      <input
        type="date"
        className="dev-rbinput dev-rbdate"
        value={datePart}
        onChange={(e) => onChange(e.target.value)}
      />
    );
  }
  if (t === "integer" || t === "positiveInt" || t === "unsignedInt" || t === "decimal") {
    return (
      <input
        type="number"
        step={t === "decimal" ? "any" : "1"}
        className="dev-rbinput dev-rbnum"
        value={value}
        onChange={(e) => onChange(e.target.value)}
      />
    );
  }
  if (t === "code") {
    const segs = path.split(".");
    const leaf = segs[segs.length - 1];
    let ctx = "";
    if (segs.includes("name")) ctx = "name";
    else if (segs.includes("telecom")) ctx = "telecom";
    const opts =
      curatedOptions(leaf, ctx) ?? curatedOptions(leaf, resourceType) ?? curatedOptions(leaf, "");
    if (opts) {
      return (
        <select className="dev-rbinput dev-rbsel" value={value} onChange={(e) => onChange(e.target.value)}>
          <option value="">—</option>
          {opts.map((o) => (
            <option key={o} value={o}>
              {o}
            </option>
          ))}
        </select>
      );
    }
  }
  return <input className="dev-rbinput" value={value} onChange={(e) => onChange(e.target.value)} />;
}

/** Quantity widget: numeric value + unit fields writing {value, unit} JSON. */
function QuantityInput({
  raw,
  onSet,
}: {
  raw: string;
  onSet: (value: string, unit: string) => void;
}) {
  let obj: { value?: unknown; unit?: unknown; code?: unknown } = {};
  try {
    const p = JSON.parse(raw);
    if (p && typeof p === "object") obj = p as typeof obj;
  } catch {
    // not JSON-shaped yet — treat as empty
  }
  const num = obj.value;
  const unit =
    typeof obj.unit === "string" ? obj.unit : typeof obj.code === "string" ? obj.code : "";
  return (
    <span className="dev-rbqty">
      <input
        type="number"
        step="any"
        className="dev-rbinput dev-rbqtyval"
        placeholder="value"
        value={num === undefined || num === null ? "" : String(num)}
        onChange={(e) => onSet(e.target.value, unit)}
      />
      <input
        className="dev-rbinput dev-rbqtyunit"
        placeholder="unit (e.g. mg)"
        value={unit}
        onChange={(e) => onSet(num === undefined || num === null ? "" : String(num), e.target.value)}
      />
    </span>
  );
}

/**
 * Context the recursive form renderer needs from the pane: writers +
 * reference browse + curated-binding context. Kept as a plain object so the
 * recursion passes one prop.
 */
export interface FormCtx {
  resourceType: string;
  setAtPath: (path: string, value: unknown, del: boolean) => void;
  setQuantityObj: (path: string, patch: Record<string, unknown>, delKeys: string[]) => void;
  appendAt: (path: string, def: unknown) => void;
  removeAt: (path: string) => void;
  browseReferences: (path: string, targets: string[]) => void;
  refBrowsePath: string | null;
  refCandidates: RefCandidate[];
  refTargets: string[];
}

/**
 * Recursive structured group: renders the schema children of one object
 * value as nested typed widgets (Coding under Code, value/unit under
 * Quantity, …). Raw JSON only for hatch/unknown shapes.
 */
function StructuredGroup({
  obj,
  schema,
  prefix,
  depth,
  ctx,
}: {
  obj: Record<string, unknown>;
  schema: SchemaNode;
  prefix: string;
  depth: number;
  ctx: FormCtx;
}) {
  const fields = fieldsFor(obj, schema, prefix, depth > 0);
  if (fields.length === 0 && depth > 0) {
    return <div className="dev-rbgroup-empty">(empty group — add fields below or via JSON)</div>;
  }
  return (
    <div className={depth === 0 ? "dev-rbgroup-root" : "dev-rbgroup"}>
      {fields.map((f) => {
        const leaf = f.node.name;
        const segs = f.path.replace(/#\d+$/, "").split(".");
        const required = f.node.cardinality === "1..1";
        if (isStructuredType(f.node)) {
          const childObj =
            f.value && typeof f.value === "object" && !Array.isArray(f.value)
              ? (f.value as Record<string, unknown>)
              : {};
          return (
            <div key={f.path} className="dev-rbgroupitem">
              <div className="dev-rbgrouplabel">
                {leaf}
                {required && <span className="dev-rbreq"> *</span>}
                <span className="dev-rbsub"> {f.node.type} {f.node.cardinality ?? ""}</span>
                {f.index !== null && (
                  <button
                    type="button"
                    className="dev-rbdelbtn"
                    title={`remove this ${leaf} element`}
                    aria-label={`remove this ${leaf} element`}
                    onClick={() => ctx.removeAt(f.path)}
                  >
                    ✕
                  </button>
                )}
                {(f.node.cardinality === "0..*" || f.index !== null) && (
                  <button
                    type="button"
                    className="dev-rbaddbtn"
                    title={`add another ${leaf} element`}
                    aria-label={`add another ${leaf} element`}
                    onClick={() => ctx.appendAt(f.path.replace(/#\d+$/, ""), typeof f.value === "object" && f.value !== null && !Array.isArray(f.value) ? {} : Array.isArray(f.value) ? "" : typeof f.value)}
                  >
                    +
                  </button>
                )}
              </div>
              <StructuredGroup obj={childObj} schema={f.node} prefix={f.path} depth={depth + 1} ctx={ctx} />
            </div>
          );
        }
        // Reference: text input + browse popover (reference_targets).
        const refTargets = f.node.reference_targets;
        if (refTargets?.length) {
          return (
            <div key={f.path} className="dev-rbrow">
              <label className="dev-rblabel" title={`type ${f.node.type} · cardinality ${f.node.cardinality ?? ""}`}>
                {segs.map((s, i) => (i === 0 ? s : <span key={i} className="dev-rbsub">.{s}</span>))}
                {required && <span className="dev-rbreq"> *</span>}
              </label>
              <input
                className="dev-rbinput"
                value={typeof f.value === "string" ? f.value : f.value && typeof f.value === "object" ? String((f.value as Record<string, unknown>).reference ?? "") : ""}
                placeholder={`Reference (${refTargets.join(" | ")})`}
                onChange={(e) => ctx.setAtPath(f.path, e.target.value === "" ? undefined : { reference: e.target.value }, false)}
              />
              <button
                className="dev-rbrefbtn"
                title={`Browse ${refTargets.join(" | ")} resources from the loaded dataset files`}
                aria-label={`browse ${refTargets.join(" or ")} references`}
                onClick={() => ctx.browseReferences(f.path, refTargets)}
                type="button"
              >
                ⌖
              </button>
              {ctx.refBrowsePath === f.path && (
                <RefPopover
                  targets={ctx.refTargets}
                  candidates={ctx.refCandidates}
                  onPick={(t, id) => {
                    ctx.setAtPath(f.path, { reference: `${t}/${id}` }, false);
                  }}
                  onClose={() => ctx.browseReferences("", [])}
                />
              )}
            </div>
          );
        }
        // Quantity: value + unit + system/code via the object writer.
        if (f.node.type === "Quantity") {
          const q = f.value && typeof f.value === "object" && !Array.isArray(f.value)
            ? (f.value as Record<string, unknown>)
            : {};
          return (
            <div key={f.path} className="dev-rbrow dev-rbqtyrow">
              <label className="dev-rblabel" title={`Quantity · ${f.node.cardinality ?? ""}`}>
                {leaf}{required && <span className="dev-rbreq"> *</span>}
              </label>
              <span className="dev-rbqty">
                <input
                  type="number" step="any" className="dev-rbinput dev-rbqtyval" placeholder="value"
                  value={q.value === undefined || q.value === null ? "" : String(q.value)}
                  onChange={(e) =>
                    ctx.setQuantityObj(f.path, e.target.value === "" ? {} : { value: Number(e.target.value) }, e.target.value === "" ? ["value"] : [])
                  }
                />
                <input
                  className="dev-rbinput dev-rbqtyunit" placeholder="unit"
                  value={typeof q.unit === "string" ? q.unit : ""}
                  onChange={(e) =>
                    ctx.setQuantityObj(f.path, e.target.value === "" ? {} : { unit: e.target.value }, e.target.value === "" ? ["unit"] : [])
                  }
                />
                <input
                  className="dev-rbinput dev-rbqtysystem" placeholder="system"
                  value={typeof q.system === "string" ? q.system : ""}
                  onChange={(e) =>
                    ctx.setQuantityObj(f.path, e.target.value === "" ? {} : { system: e.target.value }, e.target.value === "" ? ["system"] : [])
                  }
                />
              </span>
            </div>
          );
        }
        // Primitive (incl. choice arms already filtered): typed widget.
        return (
          <div key={f.path} className="dev-rbrow">
            <label className="dev-rblabel" title={`type ${f.node.type} · cardinality ${f.node.cardinality ?? ""}`}>
              {segs.map((s, i) => (i === 0 ? s : <span key={i} className="dev-rbsub">.{s}</span>))}
              {f.index !== null && <span className="dev-rbsub"> [{f.index}]</span>}
              {required && <span className="dev-rbreq"> *</span>}
            </label>
            <PrimitiveInput
              path={f.path}
              value={asString(f.value)}
              node={f.node}
              resourceType={ctx.resourceType}
              onChange={(raw) => {
                let value: unknown = raw;
                if (raw === "true") value = true;
                else if (raw === "false") value = false;
                else if (raw !== "" && !Number.isNaN(Number(raw))) value = Number(raw);
                ctx.setAtPath(f.path, value, raw === "");
              }}
            />
          </div>
        );
      })}
    </div>
  );
}

/** Reference browse popover (shared by flat + structured renderers). */
function RefPopover({
  targets,
  candidates,
  onPick,
  onClose,
}: {
  targets: string[];
  candidates: RefCandidate[];
  onPick: (type: string, id: string) => void;
  onClose: () => void;
}) {
  return (
    <div className="dev-rbrefpop" role="listbox">
      <div className="dev-rbrefpop-head">
        {targets.join(" | ")} from loaded data
        <button type="button" className="dev-rbrefclose" onClick={onClose}>✕</button>
      </div>
      {candidates.length === 0 ? (
        <div className="dev-rbrefempty">
          No {targets.join("/")} resources in the loaded dataset files —
          type a reference manually (e.g. {targets[0]}/id).
        </div>
      ) : (
        <div className="dev-rbreflist">
          {candidates.slice(0, 50).map((c) => (
            <button
              key={`${c.type}/${c.id}`}
              type="button"
              className="dev-rbrefitem"
              onClick={() => onPick(c.type, c.id)}
            >
              <span className="dev-rbctype">{c.type}</span>
              <span className="dev-rbcid">{c.id}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

function joinPath(base: string, name: string): string {
  return base ? `${base}.${name}` : name;
}

/** Deep-clone a value through JSON (form edits never mutate shared state). */
function clone(v: unknown): unknown {
  return v === undefined ? undefined : JSON.parse(JSON.stringify(v));
}

/**
 * Structured form tree: ONE node per schema child, carrying the CURRENT
 * resource value. Complex schema types (CodeableConcept, Coding, Quantity,
 * Reference, BackboneElement, …) render as NESTED GROUPS of their schema
 * children — raw JSON only as the deep fallback for hatch/unknown shapes.
 */
type FieldNode = {
  node: SchemaNode;
  path: string;
  value: unknown;
  /** Array index this element represents (repeatable containers). */
  index: number | null;
};

function fieldsFor(
  obj: Record<string, unknown>,
  schema: SchemaNode | null,
  prefix: string,
  /** Nested-group mode: surface absent 0..1 PRIMITIVE children so freshly
   *  added elements (e.g. a new coding) immediately show their inputs. */
  all = false
): FieldNode[] {
  if (!schema) return [];
  const out: FieldNode[] = [];
  for (const child of schema.children ?? []) {
    // Choice arms are owned by the choice dropdown rows — never duplicated here.
    if (child.hatch || child.name === "resourceType" || child.choice_group) continue;
    const path = joinPath(prefix, child.name);
    const v = obj[child.name];
    const primitive = (child.children?.length ?? 0) === 0;
    if (Array.isArray(v)) {
      v.forEach((el, i) => out.push({ node: child, path: `${path}#${i}`, value: el, index: i }));
    } else if (v !== undefined && v !== null) {
      out.push({ node: child, path, value: v, index: null });
    } else if (child.cardinality === "1..1") {
      // Required-but-missing: still surface the field so users can fill it.
      out.push({ node: child, path, value: undefined, index: null });
    } else if (all && primitive && child.cardinality !== "0..*") {
      out.push({ node: child, path, value: undefined, index: null });
    }
  }
  return out;
}

/**
 * Whether a schema node should render as a STRUCTURED nested group (its
 * schema children become widgets) rather than a raw value/JSON blob.
 * Choice-group arms are handled separately (the choice dropdown owns them).
 */
function isStructuredType(n: SchemaNode): boolean {
  if ((n.children?.length ?? 0) === 0) return false;
  if (n.choice_group) return false; // choice arms render via the group dropdown
  return true;
}

/** Value helpers for primitive widget rendering. */
function asString(v: unknown): string {
  if (v === undefined || v === null) return "";
  return typeof v === "string" ? v : JSON.stringify(v);
}

/** Derive a flat editable row set from a resource dict, guided by the schema tree. */
function rowsForResource(
  resource: Record<string, unknown>,
  tree: SchemaNode | null
): { rows: Row[]; primitives: { node: SchemaNode; path: string }[] } {
  const rows: Row[] = [];
  if (!tree) return { rows, primitives: [] };
  const walk = (node: SchemaNode, prefix: string) => {
    for (const child of node.children ?? []) {
      if (child.hatch) continue;
      const path = joinPath(prefix, child.name);
      const isComplex = (child.children?.length ?? 0) > 0;
      const v = lookup(resource, path);
      if (v !== undefined) {
        rows.push({
          path,
          value: typeof v === "string" ? v : JSON.stringify(v),
          node: child,
        });
      }
      if (isComplex) walk(child, path);
    }
  };
  walk(tree, "");
  const primitives: { node: SchemaNode; path: string }[] = [];
  const collect = (node: SchemaNode, prefix: string) => {
    for (const child of node.children ?? []) {
      if (child.hatch) continue;
      const path = joinPath(prefix, child.name);
      const isComplex = (child.children?.length ?? 0) > 0;
      if (!isComplex) primitives.push({ node: child, path });
      else collect(child, path);
    }
  };
  if (tree) collect(tree, "");
  return { rows, primitives };
}

// NOTE: rowsForResource/repeatRows above are retained for the JSON fallback
// path only; the structured form now renders via FieldNode recursion.

/** Collect one leaf row per array element for repeatable primitive arrays. */
function repeatRows(
  resource: Record<string, unknown>,
  tree: SchemaNode | null
): Row[] {
  if (!tree) return [];
  const rows: Row[] = [];
  // Walk the RESOURCE shape in parallel with the schema tree: repeatable
  // complex containers (name, telecom, …) are arrays, so a plain dotted
  // lookup misses their nested leaves — descend into each element.
  const walkRes = (resVal: unknown, node: SchemaNode, prefix: string) => {
    const arr = Array.isArray(resVal) ? resVal : [resVal];
    arr.forEach((el) => {
      if (el && typeof el === "object" && !Array.isArray(el)) {
        walkNode(el as Record<string, unknown>, node, prefix);
      }
    });
  };
  const walkNode = (obj: Record<string, unknown>, node: SchemaNode, prefix: string) => {
    for (const child of node.children ?? []) {
      if (child.hatch) continue;
      const path = joinPath(prefix, child.name);
      const isComplex = (child.children?.length ?? 0) > 0;
      const v = obj[child.name];
      if (isComplex) {
        if (v !== undefined) walkRes(v, child, path);
        continue;
      }
      if (Array.isArray(v)) {
        v.forEach((el, i) => {
          rows.push({
            path: `${path}#${i}`,
            value: typeof el === "string" ? el : JSON.stringify(el),
            node: child,
          });
        });
      }
    }
  };
  walkNode(resource, tree, "");
  return rows;
}

function lookup(obj: Record<string, unknown>, path: string): unknown {
  // Only handles simple dotted access over the template shape (good enough
  // for template seeding; everything else round-trips via the JSON editor).
  let cur: unknown = obj;
  for (const seg of path.split(".")) {
    if (cur && typeof cur === "object" && seg in (cur as Record<string, unknown>)) {
      cur = (cur as Record<string, unknown>)[seg];
    } else {
      return undefined;
    }
  }
  return cur;
}

export function ResourceBuilderPane({ transport, datasets, dataHint, initialResource = null, initialDatasetPath = null }: Props) {
  const [resourceType, setResourceType] = useState(
    initialResource && typeof initialResource.resourceType === "string" ? initialResource.resourceType : "",
  );

  const [resource, setResource] = useState<Record<string, unknown>>(initialResource ?? {});
  const [jsonText, setJsonText] = useState(initialResource ? JSON.stringify(initialResource, null, 2) : "");

  const [jsonError, setJsonError] = useState<string | null>(null);
  const [validation, setValidation] = useState<{ valid: boolean; messages: Diagnostic[] } | null>(null);
  const [saveMsg, setSaveMsg] = useState<string | null>(null);
  const [datasetPath, setDatasetPath] = useState(initialDatasetPath ?? "");
  const [busy, setBusy] = useState(false);
  const [pickerText, setPickerText] = useState("");
  const [tree, setTree] = useState<SchemaNode | null>(null);
  // Reference browse popover state: path of the Reference row it is attached to + candidates.
  const [refBrowse, setRefBrowse] = useState<{ path: string; targets: string[]; candidates: RefCandidate[] } | null>(null);

  /** Load candidates for a Reference field from the loaded dataset files. */
  const browseReferences = async (path: string, targets: string[]) => {
    try {
      const pools = await Promise.all(
        datasets.slice(0, 4).map((d) => transport.dataset(d).catch(() => null))
      );
      const seen = new Set<string>();
      const candidates: RefCandidate[] = [];
      for (const pool of pools) {
        if (!pool?.ok) continue;
        for (const r of pool.resources ?? []) {
          const t = String((r as Record<string, unknown>).resourceType ?? "");
          const id = String((r as Record<string, unknown>).id ?? "");
          if (!t || !id || !targets.includes(t)) continue;
          const key = `${t}/${id}`;
          if (seen.has(key)) continue;
          seen.add(key);
          candidates.push({ type: t, id });
        }
      }
      candidates.sort((a, b) => a.type.localeCompare(b.type) || a.id.localeCompare(b.id));
      setRefBrowse({ path, targets, candidates });
    } catch {
      setRefBrowse({ path, targets, candidates: [] });
    }
  };
  const jsonAreaRef = useRef<HTMLTextAreaElement | null>(null);

  useEffect(() => {
    if (!resourceType) return;
    let alive = true;
    transport
      .schemaTree(resourceType, 4)
      .then((r) => {
        if (alive) setTree(r.root ?? null);
      })
      .catch(() => {
        if (alive) setTree(null);
      });
    return () => {
      alive = false;
    };
  }, [resourceType, transport]);

  useEffect(() => {
    if (datasets.length && !datasetPath) setDatasetPath(datasets[0]);
  }, [datasets, datasetPath]);

  const loadTemplate = (type: string) => {
    setResourceType(type);
    const tpl = TEMPLATES[type];
    setResource(tpl ? { ...(tpl as Record<string, unknown>) } : { resourceType: type });
  };

  // The JSON editor is the source of truth once the user edits it; the
  // template seeds it. Form rows read from the same parsed resource.
  useEffect(() => {
    setJsonText(JSON.stringify(resource, null, 2));
  }, [resource]);

  const applyJson = (text: string) => {
    setJsonText(text);
    try {
      const parsed = JSON.parse(text);
      if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) {
        setResource(parsed as Record<string, unknown>);
        setJsonError(null);
      } else {
        setJsonError("Resource must be a JSON object");
      }
    } catch (e) {
      setJsonError(`invalid JSON: ${(e as Error).message}`);
    }
  };

  const setField = (path: string, raw: string) => {
    // Typed parse: try boolean/int/float, else keep string.
    let value: unknown = raw;
    if (raw === "true") value = true;
    else if (raw === "false") value = false;
    else if (raw !== "" && !Number.isNaN(Number(raw))) value = Number(raw);
    setAtPath(path, value, raw === "");
  };

  /** Set (or delete on empty) a value at a dotted or array-indexed (#N) path. */
  const setAtPath = (path: string, value: unknown, del: boolean) => {
    const next = { ...resource } as Record<string, unknown>;
    const segs = path.split(".");
    let cur: Record<string, unknown> = next;
    for (let i = 0; i < segs.length - 1; i++) {
      const seg = segs[i];
      if (!cur[seg] || typeof cur[seg] !== "object") cur[seg] = {};
      let v: unknown = cur[seg];
      // Repeatable complex containers are arrays — descend into the element
      // whose sub-path the row addresses (affordance rows are per-element).
      if (Array.isArray(v)) v = v[0];
      cur = (v ?? {}) as Record<string, unknown>;
    }
    const leafSeg = segs[segs.length - 1];
    const hashIdx = leafSeg.indexOf("#");
    if (hashIdx >= 0) {
      const leaf = leafSeg.slice(0, hashIdx);
      const idx = Number(leafSeg.slice(hashIdx + 1));
      const arr = cur[leaf];
      if (Array.isArray(arr) && idx >= 0 && idx < arr.length) {
        const copy = [...arr];
        if (del) copy.splice(idx, 1);
        else copy[idx] = value;
        cur[leaf] = copy;
      }
    } else if (del) delete cur[leafSeg];
    else cur[leafSeg] = value;
    setResource(next);
  };

  /** Choice[x] selection: write the chosen arm key and remove sibling arms. */
  const setChoiceArm = (group: string, armName: string, raw: string) => {
    let value: unknown = raw;
    if (raw === "true") value = true;
    else if (raw === "false") value = false;
    else if (raw !== "" && !Number.isNaN(Number(raw))) value = Number(raw);
    const next = { ...resource } as Record<string, unknown>;
    const arms = scanChoiceArms(tree, group);
    for (const a of arms) delete next[a.name];
    if (raw !== "") next[armName] = value;
    setResource(next);
  };

  /** Quantity {value, unit} writer. */
  const setQuantity = (path: string, valueStr: string, unit: string) => {
    if (valueStr === "" && unit === "") setAtPath(path, "", true);
    else {
      const n = valueStr === "" ? null : Number(valueStr);
      const obj: Record<string, unknown> = n === null || Number.isNaN(n) ? {} : { value: n };
      if (unit) obj.unit = unit;
      setAtPath(path, obj, false);
    }
  };

  /** Append one element to a (possibly absent) array field in the resource. */
  /** Remove the element addressed by a #N (or plain dotted) path. */
  const removeAt = (path: string) => setAtPath(path, "", true);

  /**
   * Object writer for structured leaf groups (Quantity, Reference, …):
   * merges `patch` into the object at `path` and deletes `delKeys`.
   */
  const setQuantityObj = (path: string, patch: Record<string, unknown>, delKeys: string[]) => {
    const next = { ...resource } as Record<string, unknown>;
    const segs = path.split(".");
    let cur: Record<string, unknown> = next;
    for (let i = 0; i < segs.length - 1; i++) {
      const seg = segs[i];
      if (!cur[seg] || typeof cur[seg] !== "object") cur[seg] = {};
      let v: unknown = cur[seg];
      if (Array.isArray(v)) v = v[0];
      cur = (v ?? {}) as Record<string, unknown>;
    }
    const leafSeg = segs[segs.length - 1];
    const hashIdx = leafSeg.indexOf("#");
    let leaf = leafSeg;
    let target: Record<string, unknown> = cur;
    if (hashIdx >= 0) {
      leaf = leafSeg.slice(0, hashIdx);
      const idx = Number(leafSeg.slice(hashIdx + 1));
      const arr = cur[leaf];
      if (!Array.isArray(arr) || idx < 0 || idx >= arr.length) return;
      const el = arr[idx];
      target = el && typeof el === "object" ? (el as Record<string, unknown>) : (arr[idx] = {});
    }
    let obj = target[leaf];
    if (!obj || typeof obj !== "object" || Array.isArray(obj)) obj = target[leaf] = {};
    const merged = { ...(obj as Record<string, unknown>), ...patch };
    for (const k of delKeys) delete merged[k];
    if (Object.keys(merged).length === 0) delete target[leaf];
    else target[leaf] = merged;
    setResource(next);
  };

  const appendAt = (path: string, def: unknown) => {
    const next = { ...resource } as Record<string, unknown>;
    const segs = path.split(".");
    let cur: Record<string, unknown> = next;
    for (let i = 0; i < segs.length - 1; i++) {
      const seg = segs[i];
      if (!cur[seg] || typeof cur[seg] !== "object") cur[seg] = {};
      cur = cur[seg] as Record<string, unknown>;
    }
    const leaf = segs[segs.length - 1];
    const existing = cur[leaf];
    if (Array.isArray(existing)) cur[leaf] = [...existing, def];
    else if (existing === undefined || existing === null) cur[leaf] = [def];
    else cur[leaf] = [existing, def];
    setResource(next);
  };

  /** Choice groups present in the schema (from the tree, deduped). */
  const choiceGroups = useMemo(() => {
    if (!tree) return [] as string[];
    const seen = new Set<string>();
    const walk = (n: SchemaNode) => {
      for (const c of n.children ?? []) {
        if (c.hatch) continue;
        if (c.choice_group) seen.add(c.choice_group);
        if ((c.children?.length ?? 0) > 0) walk(c);
      }
    };
    walk(tree);
    return [...seen];
  }, [tree]);

  const selectedChoiceArm = (group: string): { arm: SchemaNode; value: string } | null => {
    const arms = scanChoiceArms(tree, group);
    for (const a of arms) {
      const v = resource[a.name];
      if (v !== undefined) {
        return { arm: a, value: typeof v === "string" ? v : JSON.stringify(v) };
      }
    }
    return null;
  };

  // Schema-valid root fields for the add-element picker: repeatables can
  // always take another element; 0..1 fields only until present.
  const rootFields = useMemo(() => {
    if (!tree) return [];
    return (tree.children ?? [])
      .filter((c) => !c.hatch && c.name !== "id")
      .map((c) => ({
        name: c.name,
        cardinality: c.cardinality,
        repeat: c.cardinality === "0..*",
        complex: (c.children?.length ?? 0) > 0,
        present: lookup(resource, c.name) !== undefined,
      }));
  }, [tree, resource]);

  const [addSel, setAddSel] = useState("");

  const addField = () => {
    const f = rootFields.find((x) => x.name === addSel);
    if (!f) return;
    appendAt(f.name, f.complex ? {} : "");
    setAddSel("");
  };

  const validate = async () => {
    setBusy(true);
    setSaveMsg(null);
    try {
      const r = await transport.resourceValidate(resource);
      setValidation({ valid: r.valid, messages: r.diagnostics ?? [] });
    } catch (e) {
      setValidation({ valid: false, messages: [{ message: (e as Error).message, code: "INPUT_ERROR" }] });
    } finally {
      setBusy(false);
    }
  };

  const save = async () => {
    setBusy(true);
    setSaveMsg(null);
    try {
      const v = await transport.resourceValidate(resource);
      if (!v.valid) {
        setValidation({ valid: false, messages: v.diagnostics ?? [] });
        return;
      }
      setValidation({ valid: true, messages: [] });
      await transport.resourceSave(resource, datasetPath);
      setSaveMsg(`Saved to ${datasetPath} — restart the kernel to load new data.`);
    } catch (e) {
      setSaveMsg(`save failed: ${(e as Error).message}`);
    } finally {
      setBusy(false);
    }
  };

  const filtered = COMMON_TYPES.filter(
    (t) => !pickerText || t.toLowerCase().includes(pickerText.toLowerCase())
  );

  return (
    <div className="dev-rbpane">
      <div className="dev-rbbar">
        <span className="dev-pane-label">Resource builder</span>
        <input
          className="dev-rbpicker"
          placeholder="search resource type…"
          value={pickerText}
          onChange={(e) => setPickerText(e.target.value)}
        />
        <select
          className="dev-rbtype"
          value={resourceType}
          onChange={(e) => loadTemplate(e.target.value)}
        >
          <option value="">choose type…</option>
          {filtered.map((t) => (
            <option key={t} value={t}>
              {t}
            </option>
          ))}
        </select>
        {Object.keys(TEMPLATES).includes(resourceType) && (
          <button className="dev-rbtpl" onClick={() => loadTemplate(resourceType)}>
            reload template
          </button>
        )}
      </div>

      <div className="dev-rbtemplates">
        {Object.keys(TEMPLATES).map((t) => (
          <button key={t} className="dev-rbtpl" onClick={() => loadTemplate(t)}>
            {t} template
          </button>
        ))}
      </div>

      {!resourceType ? (
        <div className="dev-vdhint dev-rbenhance">
          Pick a resource type (or a starter template) to begin. The form below
          is guided by the FHIR schema tree; the JSON editor is always
          available for anything the form does not surface.
        </div>
      ) : (
        <div className="dev-rbmain">
          <div className="dev-rbform">
            <div className="dev-rbformhead">
              form <span className="dev-rbsub">({resourceType}) — template helpers, JSON is authoritative</span>
            </div>
            {choiceGroups.map((group) => {
              const arms = scanChoiceArms(tree, group);
              const sel = selectedChoiceArm(group);
              // Hide groups with no active arm AND no meaningful choice
              // remaining (only render the picker when the user can act).
              if (!sel && arms.length < 2) return null;
              return (
                <div key={group} className="dev-rbrow dev-rbchoicerow">
                  <label className="dev-rblabel" title={`choice group ${group} — pick one arm (SDC-style: only the active arm shows)`}>
                    {group}
                  </label>
                  <select
                    className="dev-rbinput dev-rbsel dev-rbchoicesel"
                    title={`choose the ${group} arm`}
                    aria-label={`choice arm for ${group}`}
                    value={sel ? sel.arm.name : ""}
                    onChange={(e) => {
                      const armName = e.target.value;
                      const arm = arms.find((a) => a.name === armName);
                      if (!arm) return;
                      // Seed a sensible default per arm type; refine below.
                      const def = arm.type === "boolean" ? "false" : arm.type === "integer" || arm.type === "decimal" ? "0" : "";
                      setChoiceArm(group, arm.name, def);
                    }}
                  >
                    <option value="">—</option>
                    {arms.map((a) => (
                      <option key={a.name} value={a.name}>
                        {a.name.replace(/(Boolean|DateTime|Integer|Decimal|String|Code|Quantity|Range|Period|Ratio)$/i, "")} ({a.type})
                      </option>
                    ))}
                  </select>
                  {sel && sel.arm.type === "Quantity" ? (
                    <span className="dev-rbchoicewidget dev-rbqty">
                      <input
                        type="number" step="any" className="dev-rbinput dev-rbqtyval" placeholder="value"
                        value={typeof (resource[sel.arm.name] as Record<string, unknown> | undefined)?.value === "number"
                          ? String((resource[sel.arm.name] as Record<string, unknown>).value) : ""}
                        onChange={(e) => setQuantityObj(sel.arm.name, e.target.value === "" ? {} : { value: Number(e.target.value) }, e.target.value === "" ? ["value"] : [])}
                      />
                      <input
                        className="dev-rbinput dev-rbqtyunit" placeholder="unit (e.g. mg)"
                        value={typeof (resource[sel.arm.name] as Record<string, unknown> | undefined)?.unit === "string"
                          ? (resource[sel.arm.name] as Record<string, unknown>).unit as string : ""}
                        onChange={(e) => setQuantityObj(sel.arm.name, e.target.value === "" ? {} : { unit: e.target.value }, e.target.value === "" ? ["unit"] : [])}
                      />
                      <input
                        className="dev-rbinput dev-rbqtysystem" placeholder="system (UCUM)"
                        value={typeof (resource[sel.arm.name] as Record<string, unknown> | undefined)?.system === "string"
                          ? (resource[sel.arm.name] as Record<string, unknown>).system as string : ""}
                        onChange={(e) => setQuantityObj(sel.arm.name, e.target.value === "" ? {} : { system: e.target.value }, e.target.value === "" ? ["system"] : [])}
                      />
                    </span>
                  ) : sel && (sel.arm.children?.length ?? 0) > 0 && !sel.arm.children!.every((c) => c.hatch) ? (
                    <span className="dev-rbchoicewidget dev-rbchoicewidget-struct">
                      <StructuredGroup
                        obj={
                          resource[sel.arm.name] && typeof resource[sel.arm.name] === "object" && !Array.isArray(resource[sel.arm.name])
                            ? (resource[sel.arm.name] as Record<string, unknown>)
                            : {}
                        }
                        schema={sel.arm}
                        prefix={sel.arm.name}
                        depth={1}
                        ctx={{
                          resourceType,
                          setAtPath,
                          setQuantityObj,
                          appendAt,
                          removeAt,
                          browseReferences,
                          refBrowsePath: refBrowse?.path ?? null,
                          refCandidates: refBrowse?.candidates ?? [],
                          refTargets: refBrowse?.targets ?? [],
                        }}
                      />
                    </span>
                  ) : sel && (
                    <span className="dev-rbchoicewidget">
                      <PrimitiveInput
                        path={sel.arm.name}
                        value={sel.value}
                        node={sel.arm}
                        resourceType={resourceType}
                        onChange={(raw) => setChoiceArm(group, sel.arm.name, raw)}
                      />
                    </span>
                  )}
                </div>
              );
            })}
            <StructuredGroup
              obj={resource}
              schema={tree!}
              prefix=""
              depth={0}
              ctx={{
                resourceType,
                setAtPath,
                setQuantityObj,
                appendAt,
                removeAt,
                browseReferences,
                refBrowsePath: refBrowse?.path ?? null,
                refCandidates: refBrowse?.candidates ?? [],
                refTargets: refBrowse?.targets ?? [],
              }}
            />
                        <div className="dev-rbaddrbar">
              <select className="dev-rbaddsel" value={addSel} onChange={(e) => setAddSel(e.target.value)}>
                <option value="">+ add data element…</option>
                {rootFields
                  .filter((f) => f.repeat || !f.present)
                  .map((f) => (
                    <option key={f.name} value={f.name}>
                      {f.name} ({f.cardinality}{f.complex ? " · complex" : ""})
                    </option>
                  ))}
              </select>
              <button
                type="button"
                className="dev-rbaddbtn"
                disabled={!addSel}
                title="append the element to the resource (JSON stays authoritative — edit deeper structure there)"
                onClick={addField}
              >
                add
              </button>
            </div>
          </div>
          <div className="dev-rbjson">
            <div className="dev-rbformhead">JSON (writer)</div>
            <textarea
              ref={jsonAreaRef}
              className="dev-rbjsonarea dev-msexpinput"
              spellCheck={false}
              value={jsonText}
              onChange={(e) => applyJson(e.target.value)}
            />
            {jsonError && <div className="dev-rberror" role="alert">{jsonError}</div>}
          </div>
        </div>
      )}

      {resourceType && (
        <div className="dev-rbsave">
          <select className="dev-rbdataset" value={datasetPath} onChange={(e) => setDatasetPath(e.target.value)}>
            {datasets.map((d) => (
              <option key={d} value={d}>
                {d}
              </option>
            ))}
          </select>
          <button className="dev-rbvalidate" disabled={busy || !!jsonError} onClick={validate}>
            Validate
          </button>
          <button
            className="dev-rbsavebtn"
            disabled={busy || !!jsonError || !datasetPath || (validation?.valid === false)}
            title={validation?.valid === false ? "fix validation errors first" : "append one NDJSON line to the dataset (kernel restart loads it)"}
            onClick={save}
          >
            Save to dataset
          </button>
          {validation && (
            <span className={validation.valid ? "dev-rbok" : "dev-rberror"}>
              {validation.valid ? "✓ valid" : validation.messages.map((m) => m.message).join("; ")}
            </span>
          )}
          {saveMsg && <span className="dev-rbsavemsg">{saveMsg}</span>}
          {dataHint && <span className="dev-stale">{dataHint}</span>}
        </div>
      )}
    </div>
  );
}
