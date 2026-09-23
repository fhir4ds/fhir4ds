import { useEffect, useMemo, useState } from "react";
import { workerRequest } from "./BootOverlay";
import {
  BUILDER_RESOURCE_TYPES,
  choiceKey,
  emptyForm,
  formToJson,
  isPrimitive,
  isRepeatable,
  jsonToForm,
  type FormState,
} from "../lib/resourceForm";
import type {
  Diagnostics,
  ResourceSchemaResult,
  SchemaField,
  ValidateResourceResult,
} from "../lib/protocol";

/**
 * C3-U2: Resource Builder pane (studio FDD §F8).
 *
 * ResourceTypePicker → resource_schema(type) → SchemaForm:
 * - top-level primitive inputs (absent ≠ "")
 * - 0..* fields as repeat rows (+ / −)
 * - choice fields ([x]) pick one concrete arm
 * - reference inputs plain text with a targets hint (S-C3-A: no
 *   autocomplete in v1)
 * - non-primitive / deeper fields surface in the passthrough drawer
 *   (S-C3-B) — edited as raw JSON, never silently dropped (INV-C3-3)
 *
 * INV-C3-2: the ONLY validation authority is validate_resource; the
 * Add-to-dataset button requires a FRESH ok (stale-ok guard: any form
 * edit after validate disables Add until revalidated).
 * INV-C3-6: the JSON preview IS the payload (same object).
 */

interface Props {
  onAddResource: (resource: Record<string, unknown>) => void;
  /** C3-U3 edit flow: prefills the builder from a dataset row. */
  prefill?: { resource: Record<string, unknown>; nonce: number } | null;
}

export function ResourceBuilderPane({ onAddResource, prefill }: Props) {
  const [resourceType, setResourceType] = useState<string>(
    prefill?.resource?.resourceType && typeof prefill.resource.resourceType === "string"
      ? prefill.resource.resourceType
      : "Patient",
  );
  const [useRaw, setUseRaw] = useState(false);
  const [schema, setSchema] = useState<ResourceSchemaResult | null>(null);
  const [form, setForm] = useState<FormState>(emptyForm("Patient"));
  const [rawText, setRawText] = useState("");
  const [validation, setValidation] = useState<ValidateResourceResult | null>(null);
  const [staleOk, setStaleOk] = useState(true);
  const [passthroughOpen, setPassthroughOpen] = useState(false);
  const [passthroughText, setPassthroughText] = useState("");
  const [passthroughError, setPassthroughError] = useState<string | null>(null);

  // Fetch the schema whenever the picked type changes.
  useEffect(() => {
    let cancelled = false;
    setSchema(null);
    setValidation(null);
    setStaleOk(true);
    if (useRaw) return;
    (async () => {
      const resp = await workerRequest({
        type: "resource_schema",
        resource_type: resourceType,
      });
      if (cancelled || !resp?.ok || !resp.envelope) return;
      const env: ResourceSchemaResult = JSON.parse(resp.envelope);
      if (!cancelled && env.resource_type === resourceType) {
        setSchema(env);
        setForm(emptyForm(resourceType));
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [resourceType, useRaw]);

  // C3-U3: when a prefill arrives (dataset-row Edit), load its schema
  // and map the resource into the form (passthrough preserves unknowns).
  const prefillNonce = prefill?.nonce ?? 0;
  useEffect(() => {
    if (!prefill || prefillNonce === 0) return;
    const rt = prefill.resource.resourceType;
    if (typeof rt !== "string") return;
    setResourceType(rt);
    setUseRaw(false);
    (async () => {
      const resp = await workerRequest({
        type: "resource_schema",
        resource_type: rt,
      });
      if (!resp?.ok || !resp.envelope) return;
      const env: ResourceSchemaResult = JSON.parse(resp.envelope);
      if (!env.ok) return;
      setSchema(env);
      setForm(prefillBuilder(prefill.resource, env.fields));
      setValidation(null);
      setStaleOk(true);
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [prefillNonce]);

  const fields = useMemo(
    () => (schema?.ok ? schema.fields : []),
    [schema],
  );

  // Passthrough drawer editing state sync.
  useEffect(() => {
    setPassthroughText(JSON.stringify(form.passthrough, null, 2));
    setPassthroughError(null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [Object.keys(form.passthrough).join(",")]);

  const draft = useMemo(() => {
    if (useRaw) {
      try {
        const parsed = JSON.parse(rawText);
        return typeof parsed === "object" && parsed !== null
          ? (parsed as Record<string, unknown>)
          : null;
      } catch {
        return null;
      }
    }
    return formToJson(form, fields);
  }, [useRaw, rawText, form, fields]);

  const invalidate = () => {
    if (validation?.valid === true) setStaleOk(false);
  };

  const setField = (name: string, value: string | string[]) => {
    invalidate();
    setForm((f) => ({ ...f, values: { ...f.values, [name]: value } }));
  };

  const setChoice = (name: string, arm: string) => {
    invalidate();
    setForm((f) => ({ ...f, choices: { ...f.choices, [name]: arm } }));
  };

  const validate = async () => {
    if (!draft) return;
    const resp = await workerRequest({
      type: "validate_resource",
      resource: draft,
    });
    if (!resp?.ok || !resp.envelope) return;
    const env: ValidateResourceResult = JSON.parse(resp.envelope);
    setValidation(env);
    setStaleOk(true);
  };

  const addToDataset = () => {
    if (!draft || !validation?.ok || !staleOk) return;
    onAddResource(draft);
    // Reset draft, keep the type for fast repeated entry.
    setForm(emptyForm(resourceType));
    setRawText("");
    setValidation(null);
    setStaleOk(true);
  };

  const canAdd = Boolean(
    draft && validation?.ok && validation.valid === true && staleOk,
  );

  const passthroughKeys = Object.keys(form.passthrough);

  return (
    <section className="pane builder-pane" data-testid="builder-pane">
      <div className="pane-header">
        <h2>Resource Builder</h2>
        <label className="builder-mode">
          <input
            type="checkbox"
            checked={useRaw}
            data-testid="builder-raw-toggle"
            onChange={(e) => {
              setUseRaw(e.target.checked);
              setValidation(null);
              setStaleOk(true);
              if (e.target.checked) {
                setRawText(
                  JSON.stringify({ resourceType }, null, 2),
                );
              }
            }}
          />{" "}
          Raw JSON
        </label>
      </div>

      <div className="builder-type">
        <label>
          Type{" "}
          <select
            data-testid="builder-type"
            value={resourceType}
            disabled={useRaw}
            onChange={(e) => setResourceType(e.target.value)}
          >
            {BUILDER_RESOURCE_TYPES.map((t: string) => (
              <option key={t} value={t}>
                {t}
              </option>
            ))}
          </select>
        </label>
      </div>

      {useRaw ? (
        <textarea
          className="builder-raw"
          data-testid="builder-raw-text"
          rows={10}
          spellCheck={false}
          value={rawText}
          onChange={(e) => {
            setRawText(e.target.value);
            invalidate();
          }}
        />
      ) : (
        <div className="builder-form" data-testid="builder-form">
          <label className="builder-row">
            <span className="builder-label">id</span>
            <input
              data-testid="builder-field-id"
              value={(form.values.id as string) ?? ""}
              onChange={(e) => setField("id", e.target.value)}
              placeholder="resource id"
            />
          </label>
          {fields.map((f) => (
            <FieldInput
              key={f.name}
              field={f}
              form={form}
              onField={setField}
              onChoice={setChoice}
            />
          ))}
          {passthroughKeys.length > 0 && (
            <div className="builder-passthrough">
              <button
                type="button"
                className="linkish"
                data-testid="builder-passthrough-toggle"
                onClick={() => setPassthroughOpen((o) => !o)}
              >
                {passthroughOpen ? "▾" : "▸"} {passthroughKeys.length} field(s)
                not shown (preserved verbatim)
              </button>
              {passthroughOpen && (
                <>
                  <textarea
                    data-testid="builder-passthrough-text"
                    rows={6}
                    spellCheck={false}
                    value={passthroughText}
                    onChange={(e) => setPassthroughText(e.target.value)}
                  />
                  {passthroughError && (
                    <div className="diag-row diag-error">{passthroughError}</div>
                  )}
                  <button
                    type="button"
                    data-testid="builder-passthrough-apply"
                    onClick={() => {
                      try {
                        const parsed = JSON.parse(passthroughText || "{}");
                        if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed)) {
                          throw new Error("passthrough must be a JSON object");
                        }
                        invalidate();
                        setForm((f) => ({
                          ...f,
                          passthrough: parsed as Record<string, unknown>,
                        }));
                        setPassthroughError(null);
                      } catch (err) {
                        setPassthroughError(
                          err instanceof Error ? err.message : String(err),
                        );
                      }
                    }}
                  >
                    Apply passthrough
                  </button>
                </>
              )}
            </div>
          )}
        </div>
      )}

      <div className="builder-preview">
        <h3>Preview (exact validate/add payload)</h3>
        <pre data-testid="builder-preview" className="builder-pre">
          {draft ? JSON.stringify(draft, null, 2) : "—"}
        </pre>
      </div>

      <div className="builder-actions">
        <button
          type="button"
          data-testid="builder-validate"
          onClick={validate}
          disabled={!draft}
        >
          Validate
        </button>
        <button
          type="button"
          data-testid="builder-add"
          onClick={addToDataset}
          disabled={!canAdd}
          title={
            canAdd
              ? "Append to the dataset"
              : "Validate (fresh) before adding — INV-C3-2"
          }
        >
          Add to dataset
        </button>
      </div>

      {validation && (validation.valid === false || !validation.ok) && (
        <div className="diag-list" data-testid="builder-diagnostics">
          {(validation.diagnostics ?? []).length === 0 && (
            <div className="diag-row diag-error">validation failed</div>
          )}
          {(validation.diagnostics ?? []).map((d: Diagnostics, i) => (
            <div key={i} className={`diag-row diag-${d.severity}`}>
              {d.message}
            </div>
          ))}
        </div>
      )}
      {validation?.ok && validation.valid === true && (
        <div className="diag-row diag-info" data-testid="builder-valid">
          Valid {validation.resource_type}
          {validation.resource_id ? ` ${validation.resource_id}` : ""}
        </div>
      )}
    </section>
  );
}

function FieldInput({
  field,
  form,
  onField,
  onChoice,
}: {
  field: SchemaField;
  form: FormState;
  onField: (name: string, value: string | string[]) => void;
  onChoice: (name: string, arm: string) => void;
}) {
  if (field.choice) {
    const arm = form.choices[field.name] ?? "";
    return (
      <label className="builder-row builder-choice">
        <span className="builder-label">{field.name}</span>
        <select
          data-testid={`builder-choice-${field.name}`}
          value={arm}
          onChange={(e) => onChoice(field.name, e.target.value)}
        >
          <option value="">— none —</option>
          {field.types.map((t) => (
            <option key={t} value={t}>
              {choiceKey(field.name, t)}
            </option>
          ))}
        </select>
        {arm && isPrimitive([arm]) && (
          <input
            data-testid={`builder-field-${field.name}`}
            value={(form.values[field.name] as string) ?? ""}
            onChange={(e) => onField(field.name, e.target.value)}
            placeholder={field.types.includes("integer") ? "number" : "value"}
          />
        )}
      </label>
    );
  }
  if (!isPrimitive(field.types)) {
    // Complex field → raw JSON input bound to a single-slot value.
    return (
      <label className="builder-row">
        <span className="builder-label">{field.name}</span>
        <input
          data-testid={`builder-field-${field.name}`}
          value={(form.values[field.name] as string) ?? ""}
          onChange={(e) => onField(field.name, e.target.value)}
          placeholder={
            field.reference_targets.length
              ? `${field.reference_targets[0]}/id`
              : "JSON"
          }
        />
        {field.reference_targets.length > 0 && (
          <span className="builder-hint">
            targets: {field.reference_targets.join(", ")}
          </span>
        )}
      </label>
    );
  }
  if (isRepeatable(field.cardinality)) {
    const rows = Array.isArray(form.values[field.name])
      ? (form.values[field.name] as string[])
      : form.values[field.name] !== undefined
        ? [form.values[field.name] as string]
        : [""];
    return (
      <div className="builder-row builder-repeat">
        <span className="builder-label">{field.name}</span>
        {rows.map((r, i) => (
          <span key={i} className="builder-repeat-row">
            <input
              data-testid={`builder-field-${field.name}-${i}`}
              value={r}
              onChange={(e) => {
                const next = [...rows];
                next[i] = e.target.value;
                onField(field.name, next);
              }}
              placeholder={field.types[0]}
            />
          </span>
        ))}
        <span className="builder-repeat-actions">
          <button
            type="button"
            onClick={() => onField(field.name, [...rows, ""])}
            aria-label={`add ${field.name} row`}
          >
            +
          </button>
          {rows.length > 1 && (
            <button
              type="button"
              onClick={() => onField(field.name, rows.slice(0, -1))}
              aria-label={`remove ${field.name} row`}
            >
              −
            </button>
          )}
        </span>
      </div>
    );
  }
  return (
    <label className="builder-row">
      <span className="builder-label">{field.name}</span>
      <input
        data-testid={`builder-field-${field.name}`}
        value={(form.values[field.name] as string) ?? ""}
        onChange={(e) => onField(field.name, e.target.value)}
        placeholder={field.types[0]}
      />
    </label>
  );
}

/** Prefill hook used by the dataset edit flow (C3-U3). */
export function prefillBuilder(
  resource: Record<string, unknown>,
  fields: SchemaField[],
): FormState {
  return jsonToForm(resource, fields);
}
