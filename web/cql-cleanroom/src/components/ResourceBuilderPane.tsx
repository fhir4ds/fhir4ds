import { useEffect, useMemo, useRef, useState } from "react";
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
  /** Edit mode: replace dataset row at index instead of appending. */
  onReplaceResource?: (index: number, resource: Record<string, unknown>) => void;
  /** C3-U3 edit flow: prefills the builder from a dataset row. */
  prefill?: {
    resource: Record<string, unknown>;
    nonce: number;
    /** Dataset row index this edit REPLACES (edit mode). */
    sourceIndex?: number;
  } | null;
  /** §3.2 per-patient `+` context: subject-class references default to
   *  Patient/<id>. Consumed on schema fetch; user-changeable. */
  context?: { patientId: string; nonce: number } | null;
  /** Dataset for reference pickers (target-typed + generic). */
  dataset: DatasetSpec | null;
}

export function ResourceBuilderPane({
  onAddResource,
  onReplaceResource,
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
  const [rawError, setRawError] = useState<string | null>(null);
  const [validation, setValidation] = useState<ValidateResourceResult | null>(
    null,
  );
  const [staleOk, setStaleOk] = useState(true);

  const contextNonce = context?.nonce ?? 0;
  // The builder can mount LATE (it lives in a test editor tab since
  // WORKBENCH_REORG phase 5), so the mount-time schema fetch races the
  // user's first keystrokes. Once anything is authored, the arriving
  // schema must NOT clobber the form with an empty one.
  const dirtyRef = useRef(false);
  // Type/context identity of the last schema fetch. Raw-mode toggling has
  // the same identity — skipping the reset there keeps the tree alive so
  // the raw→form round-trip can map JSON through the real schema.
  const schemaDepsRef = useRef<string>("");
  useEffect(() => {
    if (prefill && prefillNonce !== 0 && prefill.resource.resourceType === resourceType) {
      return;
    }
    if (schemaDepsRef.current === `${resourceType}|${contextNonce}`) return;
    schemaDepsRef.current = `${resourceType}|${contextNonce}`;
    const token = ++schemaReqRef.current;
    setTree(null);
    setValidation(null);
    setStaleOk(true);
    (async () => {
      const resp = await workerRequest({
        type: "resource_schema_tree",
        resource_type: resourceType,
      });
      // Token only — raw toggles re-run this effect without bumping it,
      // so an in-flight fetch must survive them (its cleanup would
      // otherwise cancel the only fetch and strand the tree on null).
      if (token !== schemaReqRef.current) return;
      if (!resp?.ok || !resp.envelope) return;
      const env: SchemaTreeResult = JSON.parse(resp.envelope);
      if (env.resource_type === resourceType) {
        setTree(env);
        // Raw mode shows no form; leave it untouched until raw exits.
        if (useRaw) return;
        setForm((f) => {
          // Late schema arrival must not clobber keystrokes made while
          // the fetch was in flight — keep authored values, but still
          // seed empty context references below.
          const fresh = dirtyRef.current
            ? { ...f, resourceType } // keep authored values, adopt the new type
            : emptyForm(resourceType);
          if (context && contextNonce !== 0 && resourceType !== "Patient") {
            const refNode = (env.root?.children ?? []).find(
              (c) =>
                (c.name === "subject" ||
                  c.name === "patient" ||
                  c.name === "beneficiary") &&
                c.type === "Reference" &&
                (c.reference_targets ?? []).includes("Patient"),
            );
            if (refNode && !fresh.values[refNode.name]) {
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
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [resourceType, useRaw, contextNonce]);

  const schemaReqRef = useRef(0);
  const prefillNonce = prefill?.nonce ?? 0;
  useEffect(() => {
    if (!prefill || prefillNonce === 0) return;
    const rt = prefill.resource.resourceType;
    if (typeof rt !== "string") return;
    setResourceType(rt);
    setUseRaw(false);
    // Claim the schema-request slot: when the prefill's type differs
    // from the current one, the type-change effect ALSO fires a fetch;
    // whoever claims last wins and the loser's response is dropped.
    const token = ++schemaReqRef.current;
    (async () => {
      const resp = await workerRequest({
        type: "resource_schema_tree",
        resource_type: rt,
      });
      if (token !== schemaReqRef.current) return; // superseded
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

  // AUTO-SAVE: debounce ~2s after draft changes → validate → commit when
  // valid (add, or replace when editing). Invalid/half-typed drafts are
  // no-ops. Empty forms never commit. Identical re-commits are skipped.
  const lastCommittedRef = useRef<string>("");
  const rawSeedRef = useRef<string>("");
  const draftJson = draft ? JSON.stringify(draft) : "";
  const prefillIndex = prefill?.sourceIndex;
  useEffect(() => {
    if (!draftJson) return; // empty form
    // Raw mode's SEEDED text ({"resourceType": "X"}) is not an authored
    // draft — entering raw mode alone must not commit anything.
    if (useRaw && draftJson === rawSeedRef.current) return;
    const timer = setTimeout(async () => {
      try {
        const resp = await workerRequest({
          type: "validate_resource",
          resource: JSON.parse(draftJson),
        });
        if (!resp?.ok || !resp.envelope) return;
        const env: ValidateResourceResult = JSON.parse(resp.envelope);
        setValidation(env);
        setStaleOk(true);
        if (env.ok && env.valid === true) {
          const commitKey = `${prefillIndex ?? "new"}:${draftJson}`;
          if (commitKey === lastCommittedRef.current) return; // no-op
          lastCommittedRef.current = commitKey;
          const committed = JSON.parse(draftJson);
          if (prefillIndex !== undefined && onReplaceResource) {
            onReplaceResource(prefillIndex, committed);
          } else {
            onAddResource(committed);
          }
        }
      } catch {
        // invalid draft mid-edit — leave as-is
      }
    }, 2000);
    return () => clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [draftJson, prefillIndex, useRaw]);

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
        <div className="pane-actions">
          <label className="builder-mode">
            Type{" "}
            <select
              data-testid="builder-type"
              value={resourceType}
              disabled={useRaw}
              onChange={(e) => {
                dirtyRef.current = false; // deliberate type switch → fresh form
                setResourceType(e.target.value);
              }}
            >
              {BUILDER_RESOURCE_TYPES.map((t: string) => (
                <option key={t} value={t}>
                  {t}
                </option>
              ))}
            </select>
          </label>
          <label className="builder-mode">
            <input
              type="checkbox"
              checked={useRaw}
              data-testid="builder-raw-toggle"
              onChange={(e) => {
                if (e.target.checked) {
                  // Round-trip hatch: seed the raw editor from the CURRENT
                  // draft (form → JSON), never a bare skeleton.
                  const seed = draft ?? { resourceType };
                  setRawText(JSON.stringify(seed, null, 2));
                  rawSeedRef.current = JSON.stringify(seed);
                  setUseRaw(true);
                } else {
                  // Back to the form only when the raw text parses —
                  // raw edits flow INTO the form (JSON → form).
                  try {
                    const parsed = JSON.parse(rawText);
                    if (
                      typeof parsed !== "object" ||
                      parsed === null ||
                      Array.isArray(parsed)
                    ) {
                      throw new Error("resource must be a JSON object");
                    }
                    if (!root) {
                      throw new Error("schema still loading — try again");
                    }
                    setForm(
                      jsonToForm(parsed as Record<string, unknown>, root),
                    );
                    // Authored from JSON: a late schema fetch must keep
                    // these values, not reset to an empty form.
                    dirtyRef.current = true;
                    setUseRaw(false);
                    setRawError(null);
                  } catch (err) {
                    setRawError(
                      err instanceof Error ? err.message : String(err),
                    );
                  }
                }
                setValidation(null);
                setStaleOk(true);
              }}
            />{" "}
            Raw JSON
          </label>
        </div>
      </div>

      <div className="pane-body">
        {useRaw ? (
          <textarea
            className="builder-raw"
            data-testid="builder-raw-text"
            rows={10}
            spellCheck={false}
            value={rawText}
            onChange={(e) => {
              setRawText(e.target.value);
              setRawError(null);
              dirtyRef.current = true;
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
                dirtyRef.current = true;
                setForm((f) => {
                  const values = { ...f.values };
                  if (v === undefined) delete values.id;
                  else values.id = v;
                  return { ...f, values };
                });
              }}
            />
            <ElementRows
              nodes={(root?.children ?? []).filter((c) => c.name !== "id")}
              values={form.values as Record<string, FieldValue>}
              resources={resourceOptions}
              onChildChange={(name, v) => {
                invalidate();
                dirtyRef.current = true;
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
        {useRaw && rawError && (
          <div className="diag-row diag-error" data-testid="builder-raw-error">
            {rawError}
          </div>
        )}

        <div className="builder-actions" hidden>
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
      </div>
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
  startOpen,
  onRemove,
}: {
  node: SchemaTreeNode;
  value: FieldValue | undefined;
  resources: Array<Record<string, unknown>>;
  onChange: (v: FieldValue | undefined) => void;
  depth?: number;
  hideHeader?: boolean;
  startOpen?: boolean;
  /** Populated-only model: drop the whole element (absent = required). */
  onRemove?: () => void;
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
          <span className="builder-row-actions">
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
            {onRemove && (
              <button
                type="button"
                className="row-remove"
                aria-label={`remove ${node.name}`}
                data-testid={`builder-remove-${node.name}`}
                onClick={onRemove}
              >
                ×
              </button>
            )}
          </span>
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
              startOpen
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
      startOpen={startOpen}
      onRemove={onRemove}
    />
  );
}

/** min cardinality ≥ 1: the element cannot be dropped from the form. */
function isRequired(node: SchemaTreeNode): boolean {
  return !!node.cardinality && node.cardinality.startsWith("1..");
}

/** Array item shape: an item itself is never repeatable. */
function singular(node: SchemaTreeNode): SchemaTreeNode {
  return isRepeatable(node.cardinality) ? { ...node, cardinality: "0..1" } : node;
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
  startOpen,
  onRemove,
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
  /** Forwarded to NestedObject: items open on add. */
  startOpen?: boolean;
  /** Drop the element (ElementRows wires it; never inside items). */
  onRemove?: () => void;
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
        {onRemove && <RemoveBtn node={node} onRemove={onRemove} tid={tid} />}
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
        {onRemove && <RemoveBtn node={node} onRemove={onRemove} tid={tid} />}
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
        {onRemove && <RemoveBtn node={node} onRemove={onRemove} tid={tid} />}
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
        {onRemove && <RemoveBtn node={node} onRemove={onRemove} tid={tid} />}
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
        {onRemove && <RemoveBtn node={node} onRemove={onRemove} tid={tid} />}
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
      startOpen={startOpen}
      onRemove={onRemove}
    />
  );
}

/** Element-remove × (populated-only model; absent = required element). */
function RemoveBtn({
  node,
  onRemove,
  tid,
}: {
  node: SchemaTreeNode;
  onRemove: () => void;
  tid: (base: string) => string;
}) {
  return (
    <span className="builder-row-actions">
      <button
        type="button"
        className="row-remove"
        aria-label={`remove ${node.name}`}
        title="Remove this element from the resource"
        data-testid={tid(`builder-remove-${node.name}`)}
        onClick={(e) => {
          e.preventDefault(); // rows can be <label> — keep focus off inputs
          onRemove();
        }}
      >
        ×
      </button>
    </span>
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
  startOpen,
  onRemove,
}: {
  node: SchemaTreeNode;
  value: ObjectValue;
  resources: Array<Record<string, unknown>>;
  onChange: (v: FieldValue | undefined) => void;
  depth: number;
  /** Choice arms render headerless under their picker. */
  hideHeader?: boolean;
  /** Explicit open state (repeatable items open on add). */
  startOpen?: boolean;
  /** Drop the whole element (wired by ElementRows; absent = required). */
  onRemove?: () => void;
}) {
  // Populated objects stay open; EMPTY ones start collapsed (a brand-new
  // resource shows just the field names; anything with data is laid out).
  // startOpen overrides (user explicitly added the item).
  const hasData =
    startOpen ??
    (Object.keys(value.children).length > 0 ||
      Object.keys(value.passthrough).length > 0);
  const [open, setOpen] = useState(hasData);
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
          {onRemove && (
            <span className="builder-row-actions">
              <button
                type="button"
                className="row-remove"
                aria-label={`remove ${node.name}`}
                title="Remove this element from the resource"
                data-testid={`builder-remove-${node.name}`}
                onClick={(e) => {
                  e.stopPropagation(); // the head row toggles collapse
                  onRemove();
                }}
              >
                ×
              </button>
            </span>
          )}
        </div>
      )}
      {open && (
        <div className="builder-tree-children">
          <ElementRows
            scope={node.name}
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
 * Populated-only element list (Joel's model): rows render ONLY for
 * elements with data, in schema order; an "+ add element…" select
 * (native, type-ahead) offers every ABSENT element — a 0..1 element
 * leaves the list once present and returns when its × drops it;
 * choice arms group under their base; min-1 elements have no ×.
 */
type ArmGroup =
  | { kind: "single"; node: SchemaTreeNode }
  | { kind: "choice"; base: string; arms: SchemaTreeNode[] };

function groupArms(nodes: SchemaTreeNode[]): ArmGroup[] {
  const groups: ArmGroup[] = [];
  const byGroup = new Map<string, ArmGroup & { kind: "choice" }>();
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
  return groups;
}

function ElementRows({
  nodes,
  values,
  resources,
  onChildChange,
  depth,
  scope,
}: {
  nodes: SchemaTreeNode[];
  values: Record<string, FieldValue>;
  resources: Array<Record<string, unknown>>;
  onChildChange: (name: string, v: FieldValue | undefined) => void;
  depth: number;
  /** Parent node name when nested (suffixes the add-element testid). */
  scope?: string;
}) {
  const groups = groupArms(nodes);
  const isPopulated = (g: ArmGroup) =>
    g.kind === "single"
      ? values[g.node.name] !== undefined
      : g.arms.some((a) => values[a.name] !== undefined);
  const populated = groups.filter(isPopulated);
  const addable = groups.filter((g) => !isPopulated(g));

  const add = (key: string) => {
    const g = addable.find((x) =>
      x.kind === "single" ? x.node.name === key : x.base === key,
    );
    if (!g) return;
    if (g.kind === "single") {
      const n = g.node;
      onChildChange(
        n.name,
        isRepeatable(n.cardinality)
          ? {
              kind: "items",
              items: [{ key: newKey(), value: defaultValue(singular(n)) }],
            }
          : defaultValue(n),
      );
    } else {
      // Choice group: seed the first arm; the arm select can switch.
      const arm = g.arms[0];
      if (arm) onChildChange(arm.name, defaultValue(singular(arm)));
    }
  };

  return (
    <>
      {populated.map((g) =>
        g.kind === "single" ? (
          <FieldRow
            key={g.node.name}
            node={g.node}
            value={values[g.node.name]}
            resources={resources}
            onChange={(v) => onChildChange(g.node.name, v)}
            depth={depth}
            onRemove={
              isRequired(g.node)
                ? undefined
                : () => onChildChange(g.node.name, undefined)
            }
          />
        ) : (
          <ChoiceGroup
            key={`cg-${g.base}`}
            base={g.base}
            arms={g.arms}
            values={values}
            resources={resources}
            onChildChange={onChildChange}
            depth={depth}
            onRemove={
              g.arms.every(isRequired)
                ? undefined
                : () => {
                    for (const a of g.arms) {
                      if (values[a.name] !== undefined) {
                        onChildChange(a.name, undefined);
                      }
                    }
                  }
            }
          />
        ),
      )}
      {addable.length > 0 && (
        <div className="builder-add-row">
          <select
            data-testid={scope ? `builder-add-element-${scope}` : "builder-add-element"}
            value=""
            aria-label="add element"
            title="Add a data element to the resource"
            onChange={(e) => {
              if (e.target.value) add(e.target.value);
            }}
          >
            <option value="">+ add element…</option>
            {addable.map((g) => {
              const node =
                g.kind === "single" ? g.node : { name: g.base, cardinality: "0..1" };
              return (
                <option
                  key={g.kind === "single" ? g.node.name : `cg-${g.base}`}
                  value={g.kind === "single" ? g.node.name : g.base}
                >
                  {node.name}
                  {node.cardinality ? ` (${node.cardinality})` : ""}
                </option>
              );
            })}
          </select>
        </div>
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
  onRemove,
}: {
  base: string;
  arms: SchemaTreeNode[];
  values: Record<string, FieldValue>;
  resources: Array<Record<string, unknown>>;
  onChildChange: (name: string, v: FieldValue | undefined) => void;
  depth: number;
  /** Drop the populated arm (ElementRows wires it; absent = required). */
  onRemove?: () => void;
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
        {onRemove && (
          <span className="builder-row-actions">
            <button
              type="button"
              className="row-remove"
              aria-label={`remove ${base}`}
              title="Remove this element from the resource"
              data-testid={`builder-remove-${base}`}
              onClick={onRemove}
            >
              ×
            </button>
          </span>
        )}
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
