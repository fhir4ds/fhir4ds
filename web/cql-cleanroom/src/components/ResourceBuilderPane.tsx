import { useEffect, useMemo, useState } from "react";
import { workerRequest } from "./BootOverlay";
import {
  BUILDER_RESOURCE_TYPES,
  emptyForm,
  emptyObject,
  formToJson,
  isPrimitiveType,
  isRepeatable,
  jsonToForm,
  newKey,
  scalarValue,
  type FieldValue,
  type FormState,
  type ObjectValue,
} from "../lib/resourceForm";
import type {
  Diagnostics,
  DatasetSpec,
  SchemaTreeResult,
  SchemaTreeNode,
  ValidateResourceResult,
} from "../lib/protocol";

/**
 * v2 recursive Resource Builder (FEATURE_CLEANROOM_TEST_DATA_AUTHORING §3.3).
 *
 * Drives off resource_schema_tree: primitives render inputs, References
 * render pickers (dataset resources + free text, emitting {reference}
 * objects — F4), complex/backbone nodes render NESTED sub-forms, arrays
 * render add/remove item lists with persistent _keys, and hatch nodes
 * (depth cap / extension / contained / unknown) render JSON hatches.
 * Passthrough drawers exist at EVERY object level (INV-5).
 *
 * INV-C3-2 unchanged: validate_resource is the only authority; Add
 * requires a FRESH ok (stale guard on any edit).
 * INV-C3-6: preview == payload.
 */

interface Props {
  onAddResource: (resource: Record<string, unknown>) => void;
  /** C3-U3 edit flow: prefills the builder from a dataset row. */
  prefill?: { resource: Record<string, unknown>; nonce: number } | null;
  /** §3.2 per-patient `+` context: subject-class references default to
   *  Patient/<id>. Consumed on schema fetch; user-changeable. */
  context?: { patientId: string; nonce: number } | null;
  /** Dataset for reference pickers (target-typed + generic). */
  dataset: DatasetSpec | null;
}

export function ResourceBuilderPane({
  onAddResource,
  prefill,
  context,
  dataset,
}: Props) {
  const [resourceType, setResourceType] = useState<string>(
    prefill?.resource?.resourceType &&
      typeof prefill.resource.resourceType === "string"
      ? prefill.resource.resourceType
      : "Patient",
  );
  const [useRaw, setUseRaw] = useState(false);
  const [tree, setTree] = useState<SchemaTreeResult | null>(null);
  const [form, setForm] = useState<FormState>(emptyForm("Patient"));
  const [rawText, setRawText] = useState("");
  const [validation, setValidation] = useState<ValidateResourceResult | null>(
    null,
  );
  const [staleOk, setStaleOk] = useState(true);

  const contextNonce = context?.nonce ?? 0;
  useEffect(() => {
    let cancelled = false;
    setTree(null);
    setValidation(null);
    setStaleOk(true);
    if (useRaw) return;
    (async () => {
      const resp = await workerRequest({
        type: "resource_schema_tree",
        resource_type: resourceType,
      });
      if (cancelled || !resp?.ok || !resp.envelope) return;
      const env: SchemaTreeResult = JSON.parse(resp.envelope);
      if (!cancelled && env.resource_type === resourceType) {
        setTree(env);
        setForm((f) => {
          void f;
          const fresh = emptyForm(resourceType);
          if (context && contextNonce !== 0 && resourceType !== "Patient") {
            const refNode = (env.root?.children ?? []).find(
              (c) =>
                (c.name === "subject" ||
                  c.name === "patient" ||
                  c.name === "beneficiary") &&
                c.type === "Reference" &&
                (c.reference_targets ?? []).includes("Patient"),
            );
            if (refNode) {
              fresh.values[refNode.name] = {
                kind: "ref",
                reference: `Patient/${context.patientId}`,
              };
            }
          }
          return fresh;
        });
      }
    })();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [resourceType, useRaw, contextNonce]);

  const prefillNonce = prefill?.nonce ?? 0;
  useEffect(() => {
    if (!prefill || prefillNonce === 0) return;
    const rt = prefill.resource.resourceType;
    if (typeof rt !== "string") return;
    setResourceType(rt);
    setUseRaw(false);
    (async () => {
      const resp = await workerRequest({
        type: "resource_schema_tree",
        resource_type: rt,
      });
      if (!resp?.ok || !resp.envelope) return;
      const env: SchemaTreeResult = JSON.parse(resp.envelope);
      if (!env.ok) return;
      setTree(env);
      setForm(jsonToForm(prefill.resource, env.root));
      setValidation(null);
      setStaleOk(true);
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [prefillNonce]);

  const root = useMemo(() => (tree?.ok ? tree.root : null), [tree]);

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
    return formToJson(form, root);
  }, [useRaw, rawText, form, root]);

  const invalidate = () => {
    if (validation?.valid === true) setStaleOk(false);
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
    setForm(emptyForm(resourceType));
    setRawText("");
    setValidation(null);
    setStaleOk(true);
  };

  const canAdd = Boolean(
    draft && validation?.ok && validation.valid === true && staleOk,
  );

  const resourceOptions = useMemo(() => {
    const rs = dataset?.resources ?? [];
    return rs.filter(
      (r): r is Record<string, unknown> =>
        typeof r === "object" && r !== null && "resourceType" in r,
    );
  }, [dataset]);

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
                setRawText(JSON.stringify({ resourceType }, null, 2));
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
          <FieldRow
            node={{
              name: "id",
              type: "string",
              cardinality: "0..1",
            }}
            value={form.values.id}
            resources={resourceOptions}
            onChange={(v) => {
              invalidate();
              setForm((f) => {
                const values = { ...f.values };
                if (v === undefined) delete values.id;
                else values.id = v;
                return { ...f, values };
              });
            }}
          />
          <TreeFields
            nodes={(root?.children ?? []).filter((c) => c.name !== "id")}
            values={form.values as Record<string, FieldValue>}
            resources={resourceOptions}
            onChildChange={(name, v) => {
              invalidate();
              setForm((f) => {
                const values = { ...f.values };
                if (v === undefined) delete values[name];
                else values[name] = v;
                return { ...f, values };
              });
            }}
            depth={0}
          />
          <PassthroughDrawer
            passthrough={form.passthrough}
            onApply={(p) => {
              invalidate();
              setForm((f) => ({ ...f, passthrough: p }));
            }}
          />
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

/**
 * One field row: dispatches by node kind (primitive / reference / nested
 * object / items / hatch). Purely presentational — state flows through
 * onChange(v) with the parent owning the FieldValue.
 */
function FieldRow({
  node,
  value,
  resources,
  onChange,
  depth = 0,
  hideHeader = false,
}: {
  node: SchemaTreeNode;
  value: FieldValue | undefined;
  resources: Array<Record<string, unknown>>;
  onChange: (v: FieldValue | undefined) => void;
  depth?: number;
  hideHeader?: boolean;
}) {
  const repeatable = isRepeatable(node.cardinality);

  if (repeatable) {
    const items =
      value?.kind === "items"
        ? value.items
        : value
          ? [{ key: newKey(), value }]
          : [];
    return (
      <div className="builder-tree-group" data-testid={`builder-rep-${node.name}`}>
        <div className="builder-tree-row builder-tree-head">
          <span className="builder-caret placeholder">▾</span>
          <span className="builder-label">{node.name}</span>
          <button
            type="button"
            className="builder-item-add"
            aria-label={`add ${node.name} item`}
            data-testid={`builder-add-${node.name}`}
            onClick={() =>
              onChange({
                kind: "items",
                items: [...items, { key: newKey(), value: defaultValue(node) }],
              })
            }
          >
            +
          </button>
        </div>
        {items.map((it, i) => (
          <div
            className="builder-tree-children builder-item"
            key={it.key}
            data-testid={`builder-item-${node.name}-${i}`}
          >
            <div
              className="builder-tree-row builder-tree-head builder-item-head"
              data-testid={`builder-item-head-${node.name}-${i}`}
            >
              <span className="builder-caret placeholder" aria-hidden="true" />
              <span className="builder-label">
                {node.name} - {i + 1}
              </span>
              <button
                type="button"
                className="builder-item-remove"
                aria-label={`remove ${node.name} item ${i + 1}`}
                data-testid={`builder-remove-${node.name}-${i}`}
                onClick={() =>
                  onChange({
                    kind: "items",
                    items: items.filter((x) => x.key !== it.key),
                  })
                }
              >
                −
              </button>
            </div>
            <SingleField
              node={node}
              value={it.value}
              resources={resources}
              onChange={(v) => {
                if (v === undefined) return;
                const next = items
                  .map((x) => (x.key === it.key ? { key: it.key, value: v } : x));
                onChange({ kind: "items", items: next });
              }}
              depth={depth}
              itemIndex={i}
              hideHeader
            />
          </div>
        ))}
      </div>
    );
  }

  return (
    <SingleField
      node={node}
      value={value}
      resources={resources}
      onChange={onChange}
      depth={depth}
      hideHeader={hideHeader}
    />
  );
}

function defaultValue(node: SchemaTreeNode): FieldValue {
  if (node.hatch) return { kind: "hatch", json: "" };
  if (node.type === "Reference") return { kind: "ref", reference: "" };
  if (isPrimitiveType(node.type)) return { kind: "scalar", value: "" };
  return emptyObject();
}

function SingleField({
  node,
  value,
  resources,
  onChange,
  depth,
  itemIndex,
  hideHeader = false,
}: {
  node: SchemaTreeNode;
  value: FieldValue | undefined;
  resources: Array<Record<string, unknown>>;
  onChange: (v: FieldValue | undefined) => void;
  depth: number;
  /** Repeatable-item position: suffixes testids (builder-field-name-0). */
  itemIndex?: number;
  /** Choice arms render headerless under their picker. */
  hideHeader?: boolean;
}) {
  const tid = (base: string) =>
    itemIndex === undefined ? base : `${base}-${itemIndex}`;
  // Hatch nodes: JSON hatch (depth cap / extension / contained / unknown).
  if (node.hatch) {
    const json = value?.kind === "hatch" ? value.json : "";
    return (
      <label className="builder-tree-row builder-hatch-row">
        <span className="builder-caret placeholder" aria-hidden="true" />
        <span className="builder-label">{node.name}</span>
        <textarea
          className="builder-hatch"
          data-testid={tid(`builder-hatch-${node.name}`)}
          rows={3}
          spellCheck={false}
          placeholder="JSON"
          value={json}
          onChange={(e) =>
            onChange({ kind: "hatch", json: e.target.value })
          }
        />
      </label>
    );
  }

  if (node.type === "Reference") {
    const v = value?.kind === "ref" ? value : undefined;
    const targets = node.reference_targets ?? [];
    const options = resources
      .map((r) => {
        const rt = String(r.resourceType ?? "");
        const id = typeof r.id === "string" ? r.id : "";
        return { ref: rt && id ? `${rt}/${id}` : "", rt };
      })
      .filter((o) => o.ref && (targets.length === 0 || targets.includes(o.rt)));
    const current = v ? v.reference : "";
    const dangling =
      current !== "" &&
      !options.some((o) => o.ref === current) &&
      !/^https?:|^urn:|\/_history\//.test(current);
    return (
      <div className="builder-tree-row builder-ref">
        <span className="builder-caret placeholder" aria-hidden="true" />
        <span className="builder-label">{node.name}</span>
        <input
          list={`builder-refs-${node.name}`}
          data-testid={tid(`builder-field-${node.name}`)}
          value={current}
          placeholder={
            targets.length ? `${targets[0]}/id` : "Type/id or URL"
          }
          onChange={(e) =>
            onChange({ kind: "ref", reference: e.target.value })
          }
        />
        <datalist id={`builder-refs-${node.name}`}>
          {options.map((o) => (
            <option key={o.ref} value={o.ref} />
          ))}
        </datalist>
        {targets.length > 0 && (
          <span className="ref-target-pills">
            {targets.map((tg) => (
              <span
                key={tg}
                className="ref-target-pill"
                data-testid={tid(`builder-target-${node.name}-${tg}`)}
              >
                {tg}
              </span>
            ))}
          </span>
        )}
        {dangling && (
          <span className="builder-hint builder-warn" data-testid={tid(`builder-dangling-${node.name}`)}>
            not in dataset (allowed)
          </span>
        )}
      </div>
    );
  }

  if (isPrimitiveType(node.type)) {
    const current = scalarValue(value);
    const inputType =
      node.type === "boolean"
        ? "text"
        : node.type === "date"
          ? "date"
          : "text";
    return (
      <label className="builder-tree-row">
        <span className="builder-caret placeholder" aria-hidden="true" />
        <span className="builder-label">{node.name}</span>
        <input
          type={inputType}
          data-testid={tid(`builder-field-${node.name}`)}
          value={current}
          onChange={(e) => onChange({ kind: "scalar", value: e.target.value })}
          placeholder={node.type}
        />
      </label>
    );
  }

  // Complex datatype / backbone: nested sub-form.
  const childNodes =
    node.children && node.children.some((c) => c.name === "__hatch__")
      ? null
      : node.children;
  if (!childNodes) {
    const json = value?.kind === "hatch" ? value.json : "";
    return (
      <label className="builder-tree-row builder-hatch-row">
        <span className="builder-caret placeholder" aria-hidden="true" />
        <span className="builder-label">{node.name}</span>
        <textarea
          className="builder-hatch"
          data-testid={tid(`builder-hatch-${node.name}`)}
          rows={3}
          spellCheck={false}
          placeholder="JSON (depth cap reached)"
          value={json}
          onChange={(e) => onChange({ kind: "hatch", json: e.target.value })}
        />
      </label>
    );
  }

  const obj =
    value?.kind === "object"
      ? value
      : value
        ? undefined // mismatched shape — hatch below
        : emptyObject();

  if (value && !obj) {
    const json = value.kind === "hatch" ? value.json : "";
    return (
      <label className="builder-tree-row builder-hatch-row">
        <span className="builder-caret placeholder" aria-hidden="true" />
        <span className="builder-label">{node.name}</span>
        <textarea
          className="builder-hatch"
          data-testid={tid(`builder-hatch-${node.name}`)}
          rows={3}
          spellCheck={false}
          placeholder="JSON"
          value={json}
          onChange={(e) => onChange({ kind: "hatch", json: e.target.value })}
        />
      </label>
    );
  }

  return (
    <NestedObject
      node={node}
      value={obj!}
      resources={resources}
      onChange={onChange}
      depth={depth}
      hideHeader={hideHeader}
    />
  );
}

/**
 * A complex field rendered as a TREE ROW: caret + name on a header line,
 * children indented under left guide lines (no card chrome, no pills).
 */
function NestedObject({
  node,
  value,
  resources,
  onChange,
  depth,
  hideHeader = false,
}: {
  node: SchemaTreeNode;
  value: ObjectValue;
  resources: Array<Record<string, unknown>>;
  onChange: (v: FieldValue | undefined) => void;
  depth: number;
  /** Choice arms render headerless under their picker. */
  hideHeader?: boolean;
}) {
  const [open, setOpen] = useState(true);
  return (
    <div
      className={`builder-tree-group${open ? "" : " collapsed"}`}
      data-testid={`builder-nested-${node.name}`}
      data-depth={Math.min(depth, 6)}
    >
      {!hideHeader && (
        <div
          className="builder-tree-row builder-tree-head"
          onClick={() => setOpen((o) => !o)}
        >
          <button
            type="button"
            className="builder-caret"
            aria-label={open ? `collapse ${node.name}` : `expand ${node.name}`}
            onClick={(e) => {
              e.stopPropagation();
              setOpen((o) => !o);
            }}
          >
            {open ? "▾" : "▸"}
          </button>
          <span className="builder-label">{node.name}</span>
        </div>
      )}
      {open && (
        <div className="builder-tree-children">
          <TreeFields
            nodes={(node.children ?? []).filter((c) => c.name !== "__hatch__")}
            values={value.children}
            resources={resources}
            onChildChange={(name, v) => {
              const children = { ...value.children };
              if (v === undefined) delete children[name];
              else children[name] = v;
              onChange({ ...value, children });
            }}
            depth={depth + 1}
          />
          {(node.children ?? []).some((c) => c.name === "__hatch__") && (
            <div className="diag-row diag-info">
              deeper fields via JSON hatch at the field level
            </div>
          )}
          <PassthroughDrawer
            passthrough={value.passthrough}
            compact
            onApply={(p) => onChange({ ...value, passthrough: p })}
          />
        </div>
      )}
    </div>
  );
}

/**
 * Renders sibling field nodes as tree rows, GROUPING choice arms
 * (nodes sharing choice_group, e.g. value[x] → valueQuantity…) into a
 * single pick-one control: only the selected (populated) arm renders.
 */
function TreeFields({
  nodes,
  values,
  resources,
  onChildChange,
  depth,
}: {
  nodes: SchemaTreeNode[];
  values: Record<string, FieldValue>;
  resources: Array<Record<string, unknown>>;
  onChildChange: (name: string, v: FieldValue | undefined) => void;
  depth: number;
}) {
  // Group consecutive choice arms by their choice_group.
  const groups: Array<{ kind: "single"; node: SchemaTreeNode } | { kind: "choice"; base: string; arms: SchemaTreeNode[] }> = [];
  const byGroup = new Map<string, { kind: "choice"; base: string; arms: SchemaTreeNode[] }>();
  for (const n of nodes) {
    const g = n.choice_group;
    if (!g) {
      groups.push({ kind: "single", node: n });
      continue;
    }
    let entry = byGroup.get(g);
    if (!entry) {
      entry = { kind: "choice", base: g, arms: [] };
      byGroup.set(g, entry);
      groups.push(entry);
    }
    entry.arms.push(n);
  }

  return (
    <>
      {groups.map((g, gi) =>
        g.kind === "single" ? (
          <FieldRow
            key={g.node.name}
            node={g.node}
            value={values[g.node.name]}
            resources={resources}
            onChange={(v) => onChildChange(g.node.name, v)}
            depth={depth}
          />
        ) : (
          <ChoiceGroup
            key={`cg-${gi}`}
            base={g.base}
            arms={g.arms}
            values={values}
            resources={resources}
            onChildChange={onChildChange}
            depth={depth}
          />
        ),
      )}
    </>
  );
}

/**
 * Pick-one choice group: a dropdown selects the arm; only that arm's
 * fields render. Selection is VALUE-DRIVEN — the populated arm is the
 * selection; switching arms clears the old one and seeds the new.
 */
function ChoiceGroup({
  base,
  arms,
  values,
  resources,
  onChildChange,
  depth,
}: {
  base: string;
  arms: SchemaTreeNode[];
  values: Record<string, FieldValue>;
  resources: Array<Record<string, unknown>>;
  onChildChange: (name: string, v: FieldValue | undefined) => void;
  depth: number;
}) {
  const populated = arms.find((a) => values[a.name] !== undefined);
  const selected = populated ?? null;
  return (
    <div className="builder-choice" data-testid={`builder-choice-${base}`}>
      <div className="builder-tree-row builder-tree-head">
        <span className="builder-caret placeholder">▸</span>
        <span className="builder-label">{base}</span>
        <select
          className="builder-choice-select"
          data-testid={`builder-choice-select-${base}`}
          value={selected?.name ?? ""}
          onChange={(e) => {
          const nextName = e.target.value;
          for (const a of arms) {
            if (a.name !== nextName && values[a.name] !== undefined) {
              onChildChange(a.name, undefined);
            }
          }
          if (nextName && !values[nextName]) {
            onChildChange(nextName, defaultValue(arms.find((a) => a.name === nextName)!));
          }
        }}
        >
          <option value="">— none —</option>
          {arms.map((a) => (
            <option key={a.name} value={a.name}>
              {a.name.slice(base.length - 3)}
            </option>
          ))}
        </select>
      </div>
      {selected && (
        <div className="builder-tree-children">
          <FieldRow
            node={selected}
            value={values[selected.name]}
            resources={resources}
            onChange={(v) => onChildChange(selected.name, v)}
            depth={depth}
            hideHeader
          />
        </div>
      )}
    </div>
  );
}

function PassthroughDrawer({
  passthrough,
  onApply,
  compact = false,
}: {
  passthrough: Record<string, unknown>;
  onApply: (p: Record<string, unknown>) => void;
  compact?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const [text, setText] = useState("");
  const [error, setError] = useState<string | null>(null);
  const keys = Object.keys(passthrough);
  useEffect(() => {
    setText(JSON.stringify(passthrough, null, 2));
    setError(null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [Object.keys(passthrough).join(",")]);
  if (keys.length === 0) return null;
  return (
    <div className={`builder-passthrough${compact ? " compact" : ""}`}>
      <button
        type="button"
        className="linkish"
        data-testid="builder-passthrough-toggle"
        onClick={() => setOpen((o) => !o)}
      >
        {open ? "▾" : "▸"} {keys.length} field(s) not shown (preserved verbatim)
      </button>
      {open && (
        <>
          <textarea
            data-testid="builder-passthrough-text"
            rows={compact ? 4 : 6}
            spellCheck={false}
            value={text}
            onChange={(e) => setText(e.target.value)}
          />
          {error && <div className="diag-row diag-error">{error}</div>}
          <button
            type="button"
            data-testid="builder-passthrough-apply"
            onClick={() => {
              try {
                const parsed = JSON.parse(text || "{}");
                if (
                  typeof parsed !== "object" ||
                  parsed === null ||
                  Array.isArray(parsed)
                ) {
                  throw new Error("passthrough must be a JSON object");
                }
                onApply(parsed as Record<string, unknown>);
                setError(null);
              } catch (err) {
                setError(err instanceof Error ? err.message : String(err));
              }
            }}
          >
            Apply passthrough
          </button>
        </>
      )}
    </div>
  );
}
