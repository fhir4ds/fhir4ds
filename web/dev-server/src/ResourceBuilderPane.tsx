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

type Row = { path: string; value: string };

/** Candidate target for a Reference picker: type + id from the loaded dataset files. */
type RefCandidate = { type: string; id: string };

function joinPath(base: string, name: string): string {
  return base ? `${base}.${name}` : name;
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
      .schemaTree(resourceType, 2)
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
    const next = { ...resource } as Record<string, unknown>;
    const segs = path.split(".");
    let cur: Record<string, unknown> = next;
    for (let i = 0; i < segs.length - 1; i++) {
      const seg = segs[i];
      if (!cur[seg] || typeof cur[seg] !== "object") cur[seg] = {};
      cur = cur[seg] as Record<string, unknown>;
    }
    if (raw === "") delete cur[segs[segs.length - 1]];
    else cur[segs[segs.length - 1]] = value;
    setResource(next);
  };

  /** Append one element to a (possibly absent) array field in the resource. */
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

  const templateRows = useMemo(
    () => rowsForResource(resource, tree),
    [resource, tree]
  );

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
            {templateRows.rows.length === 0 && (
              <div className="dev-rbempty">no template fields — edit the JSON</div>
            )}
            {templateRows.rows.map((row) => {
              const prim = templateRows.primitives.find((p) => p.path === row.path);
              const refTargets = prim?.node.reference_targets;
              const parentPath = row.path.split(".").slice(0, -1).join(".");
              const leafName = row.path.split(".").slice(-1)[0];
              const parentPrim = templateRows.primitives.find((p) => p.path === parentPath);
              const parentRepeatable = parentPrim ? parentPrim.node.cardinality === "0..*" : false;
              const siblings = templateRows.rows.filter((r) => r.path !== row.path && r.path.startsWith(parentPath ? parentPath + "." : ""));
              return (
                <div key={row.path} className="dev-rbrow">
                  <label className="dev-rblabel" title={prim ? `cardinality ${prim.node.cardinality} · type ${prim.node.type}` : row.path}>
                    {row.path}
                    {prim?.node.cardinality === "1..1" && <span className="dev-rbreq"> *</span>}
                  </label>
                  {refTargets?.length ? (
                    <>
                      <input
                        className="dev-rbinput"
                        value={row.value}
                        placeholder={`Reference (${refTargets.join(" | ")})`}
                        onChange={(e) => setField(row.path, e.target.value)}
                      />
                      <button
                        className="dev-rbrefbtn"
                        title={`Browse ${refTargets.join(" | ")} resources from the loaded dataset files`}
                        onClick={() => browseReferences(row.path, refTargets)}
                        type="button"
                      >
                        ⌖
                      </button>
                    </>
                  ) : (
                    <input
                      className="dev-rbinput"
                      value={row.value}
                      onChange={(e) => setField(row.path, e.target.value)}
                    />
                  )}
                  {parentRepeatable && (
                    <button
                      type="button"
                      className="dev-rbaddbtn"
                      title={`add another ${leafName} element`}
                      onClick={() => appendAt(parentPath, "")}
                    >
                      +
                    </button>
                  )}
                  {parentRepeatable && siblings.length > 0 && (
                    <button
                      type="button"
                      className="dev-rbdelbtn"
                      title={`remove this ${leafName} element`}
                      onClick={() => {
                        const next = { ...resource } as Record<string, unknown>;
                        const segs = row.path.split(".");
                        let cur: unknown = next;
                        for (let i = 0; i < segs.length - 1; i++) {
                          cur = (cur as Record<string, unknown>)[segs[i]];
                        }
                        const parent = cur as Record<string, unknown>;
                        const arr = parent[leafName];
                        const idx = templateRows.rows.filter((r) => r.path === row.path || r.path === `${parentPath}.${leafName}`).findIndex((r) => r.path === row.path);
                        if (Array.isArray(arr)) parent[leafName] = arr.filter((_, i) => i !== idx);
                        setResource(next);
                      }}
                    >
                      ✕
                    </button>
                  )}
                  {refBrowse?.path === row.path && (
                    <div className="dev-rbrefpop" role="listbox">
                      <div className="dev-rbrefpop-head">
                        {refBrowse.targets.join(" | ")} from loaded data
                        <button type="button" className="dev-rbrefclose" onClick={() => setRefBrowse(null)}>✕</button>
                      </div>
                      {refBrowse.candidates.length === 0 ? (
                        <div className="dev-rbrefempty">
                          No {refBrowse.targets.join("/")} resources in the loaded dataset files —
                          type a reference manually (e.g. {refBrowse.targets[0]}/id).
                        </div>
                      ) : (
                        <div className="dev-rbreflist">
                          {refBrowse.candidates.slice(0, 50).map((c) => (
                            <button
                              key={`${c.type}/${c.id}`}
                              type="button"
                              className="dev-rbrefitem"
                              onClick={() => {
                                setField(row.path, `${c.type}/${c.id}`);
                                setRefBrowse(null);
                              }}
                            >
                              <span className="dev-rbctype">{c.type}</span>
                              <span className="dev-rbcid">{c.id}</span>
                            </button>
                          ))}
                        </div>
                      )}
                    </div>
                  )}
                </div>
              );
            })}
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
