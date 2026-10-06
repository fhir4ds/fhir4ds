import { useEffect, useMemo, useRef, useState } from "react";
import type { Diagnostic, Transport, SchemaTreeNode } from "./transport";

/** A node from GET /api/schema-tree (subset of fields the form needs). */
export type SchemaNode = SchemaTreeNode;

interface Props {
  transport: Transport;
  datasets: string[];
  dataHint: string | null;
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

export function ResourceBuilderPane({ transport, datasets, dataHint }: Props) {
  const [resourceType, setResourceType] = useState("");
  const [tree, setTree] = useState<SchemaNode | null>(null);
  const [resource, setResource] = useState<Record<string, unknown>>({});
  const [jsonText, setJsonText] = useState("");
  const [jsonError, setJsonError] = useState<string | null>(null);
  const [validation, setValidation] = useState<{ valid: boolean; messages: Diagnostic[] } | null>(null);
  const [saveMsg, setSaveMsg] = useState<string | null>(null);
  const [datasetPath, setDatasetPath] = useState("");
  const [busy, setBusy] = useState(false);
  const [pickerText, setPickerText] = useState("");
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

  const templateRows = useMemo(
    () => rowsForResource(resource, tree),
    [resource, tree]
  );

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
              form <span className="dev-rbsub">({resourceType})</span>
            </div>
            {templateRows.rows.length === 0 && (
              <div className="dev-rbempty">no template fields — edit the JSON</div>
            )}
            {templateRows.rows.map((row) => {
              const prim = templateRows.primitives.find((p) => p.path === row.path);
              const refTargets = prim?.node.reference_targets;
              return (
                <div key={row.path} className="dev-rbrow">
                  <label className="dev-rblabel" title={prim ? `cardinality ${prim.node.cardinality} · type ${prim.node.type}` : row.path}>
                    {row.path}
                    {prim?.node.cardinality === "1..1" && <span className="dev-rbreq"> *</span>}
                  </label>
                  {refTargets?.length ? (
                    <input
                      className="dev-rbinput"
                      value={row.value}
                      placeholder={`Reference (${refTargets.join(" | ")})`}
                      onChange={(e) => setField(row.path, e.target.value)}
                    />
                  ) : (
                    <input
                      className="dev-rbinput"
                      value={row.value}
                      onChange={(e) => setField(row.path, e.target.value)}
                    />
                  )}
                </div>
              );
            })}
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
