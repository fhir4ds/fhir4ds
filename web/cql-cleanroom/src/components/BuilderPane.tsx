import { useEffect, useMemo, useRef, useState } from "react";
import { workerRequest } from "./BootOverlay";
import { extractCqlSymbols } from "../lib/cqlSymbols";
import {
  COMPARE_OPS,
  appendDefine,
  parseDefine,
  serializeDefine,
  spliceDefine,
  type BuilderAtom,
  type BuilderExpr,
  type BuilderLiteral,
} from "../lib/cqlBuilder";

/**
 * Visual editor step 5 — expression builder. The drawer works on ONE
 * define of the ACTIVE library at a time: parse its body into the
 * HEDIS-shape model (retrieve + and-joined predicates), edit
 * structurally, and Apply splices the statement back into the library
 * text (parse-guarded). Shapes outside the grammar stay editable as
 * text — the builder never silently drops logic.
 */

interface Props {
  text: string;
  onTextChange: (text: string) => void;
}

const NEW = "__new__";

export function BuilderPane({ text, onTextChange }: Props) {
  const defines = useMemo(
    () => extractCqlSymbols(text).defines.map((d) => d.name),
    [text],
  );
  const valuesets = useMemo(
    () => extractCqlSymbols(text).valuesets.map((v) => v.name),
    [text],
  );
  const [selected, setSelected] = useState<string>(defines[0] ?? NEW);
  const [expr, setExpr] = useState<BuilderExpr | null>(null);
  const [dirty, setDirty] = useState(false);
  const [result, setResult] = useState<{ ok: boolean; detail: string } | null>(
    null,
  );
  // Apply moves BOTH text and selection; the re-parse effect must not
  // clobber the just-set expr + applied badge for that one commit.
  const appliedRef = useRef(false);

  // Re-parse when the selection changes or (when untouched) the
  // library text moves under the builder (Apply, undo, tab switch).
  useEffect(() => {
    if (appliedRef.current) {
      appliedRef.current = false;
      return;
    }
    if (selected === NEW) {
      setExpr(blankExpr());
    } else if (!dirty) {
      setExpr(parseDefine(text, selected));
    }
    setDirty(false);
    setResult(null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selected, text]);

  const preview = useMemo(
    () => (expr ? serializeDefine(expr) : ""),
    [expr],
  );

  const apply = async () => {
    if (!expr || !expr.name.trim()) return;
    const statement = serializeDefine(expr);
    const next =
      selected === NEW
        ? appendDefine(text, statement)
        : spliceDefine(text, selected, statement);
    const resp = await workerRequest({ type: "parse_cql", text: next });
    let parsed: { ok?: boolean; diagnostics?: Array<{ message: string }> } | null =
      null;
    try {
      parsed = JSON.parse(resp.envelope);
    } catch {
      /* fall through to reject */
    }
    if (resp?.ok && parsed?.ok) {
      appliedRef.current = true;
      onTextChange(next);
      if (selected === NEW) setSelected(expr.name);
      setDirty(false);
      setResult({ ok: true, detail: "applied to the active library" });
    } else {
      const msg = parsed?.diagnostics?.[0]?.message ?? "parse failed";
      setResult({ ok: false, detail: `round-trip parse failed: ${msg}` });
    }
  };

  const patch = (p: Partial<BuilderExpr>) => {
    setDirty(true);
    setResult(null);
    setExpr((e) => (e ? { ...e, ...p } : e));
  };

  const patchAtom = (i: number, a: BuilderAtom) => {
    setDirty(true);
    setResult(null);
    setExpr((e) =>
      e ? { ...e, where: e.where.map((x, j) => (j === i ? a : x)) } : e,
    );
  };

  const typeahead = useMemo(
    () =>
      Array.from(
        new Set(
          (text.match(/\[[A-Za-z][\w]*/g) ?? []).map((s) => s.slice(1)),
        ),
      ),
    [text],
  );

  if (!expr) {
    return (
      <p className="pane-hint" data-testid="builder-empty">
        No defines in this library yet — add one in the editor first.
      </p>
    );
  }

  return (
    <section className="pane builder-pane-x" data-testid="builder-pane">
      <div className="eb-row">
        <label className="eb-label" htmlFor="builder-define-select">
          Expression
        </label>
        <select
          id="builder-define-select"
          data-testid="builder-define-select"
          value={selected}
          onChange={(e) => setSelected(e.target.value)}
        >
          {defines.map((d) => (
            <option key={d} value={d}>
              {d}
            </option>
          ))}
          <option value={NEW}>+ new expression…</option>
        </select>
        {selected === NEW && (
          <input
            data-testid="builder-name"
            placeholder="expression name"
            value={expr.name}
            onChange={(e) => patch({ name: e.target.value })}
          />
        )}
      </div>

      {expr.kind === "custom" ? (
        <div>
          <p className="pane-hint">
            This body is outside the builder grammar (retrieve + where) —
            edit as text; it is applied verbatim.
          </p>
          <textarea
            className="eb-raw"
            data-testid="builder-raw"
            rows={4}
            spellCheck={false}
            value={expr.raw}
            onChange={(e) => patch({ raw: e.target.value })}
          />
        </div>
      ) : (
        <div>
          <div className="eb-row">
            <label className="eb-label" htmlFor="builder-kind">
              Shape
            </label>
            <select
              id="builder-kind"
              data-testid="builder-kind"
              value={expr.kind}
              onChange={(e) => patch({ kind: e.target.value as BuilderExpr["kind"] })}
            >
              <option value="exists">exists (boolean)</option>
              <option value="list">list of resources</option>
            </select>
          </div>
          <div className="eb-row">
            <label className="eb-label" htmlFor="builder-type">
              Retrieve
            </label>
            <input
              id="builder-type"
              data-testid="builder-type"
              list="builder-type-list"
              placeholder="resource type"
              value={expr.retrieve?.resourceType ?? ""}
              onChange={(e) =>
                patch({
                  retrieve: {
                    ...(expr.retrieve ?? { alias: "" }),
                    resourceType: e.target.value,
                  },
                })
              }
            />
            <datalist id="builder-type-list">
              {typeahead.map((t) => (
                <option key={t} value={t} />
              ))}
            </datalist>
            <input
              data-testid="builder-alias"
              placeholder="alias"
              className="eb-alias"
              value={expr.retrieve?.alias ?? ""}
              onChange={(e) =>
                patch({
                  retrieve: {
                    ...(expr.retrieve ?? { resourceType: "Patient" }),
                    alias: e.target.value,
                  },
                })
              }
            />
            <input
              data-testid="builder-valueset"
              list="builder-vs-list"
              placeholder="valueset (optional)"
              value={expr.retrieve?.valueset ?? ""}
              onChange={(e) =>
                patch({
                  retrieve: {
                    ...(expr.retrieve ?? { resourceType: "Patient", alias: "" }),
                    valueset: e.target.value || undefined,
                  },
                })
              }
            />
            <datalist id="builder-vs-list">
              {valuesets.map((v) => (
                <option key={v} value={v} />
              ))}
            </datalist>
          </div>

          <div className="eb-conds">
            {expr.where.map((a, i) => (
              <div className="eb-cond" key={i} data-testid="builder-cond-row">
                {a.type === "compare" && (
                  <>
                    <input
                      data-testid="builder-cond-path"
                      value={a.path}
                      onChange={(e) => patchAtom(i, { ...a, path: e.target.value })}
                    />
                    <select
                      data-testid="builder-cond-op"
                      value={a.op}
                      onChange={(e) => patchAtom(i, { ...a, op: e.target.value })}
                    >
                      {COMPARE_OPS.map((op) => (
                        <option key={op} value={op}>
                          {op}
                        </option>
                      ))}
                    </select>
                    <select
                      data-testid="builder-cond-litkind"
                      value={a.literal.kind}
                      onChange={(e) =>
                        patchAtom(i, {
                          ...a,
                          literal: {
                            ...a.literal,
                            kind: e.target.value as BuilderLiteral["kind"],
                          },
                        })
                      }
                    >
                      <option value="string">'…'</option>
                      <option value="number">number</option>
                      <option value="boolean">true/false</option>
                      <option value="datetime">@…</option>
                    </select>
                    {a.literal.kind === "boolean" ? (
                      <select
                        data-testid="builder-cond-value"
                        value={a.literal.value}
                        onChange={(e) =>
                          patchAtom(i, {
                            ...a,
                            literal: { ...a.literal, value: e.target.value },
                          })
                        }
                      >
                        <option value="true">true</option>
                        <option value="false">false</option>
                      </select>
                    ) : (
                      <input
                        data-testid="builder-cond-value"
                        value={a.literal.value}
                        onChange={(e) =>
                          patchAtom(i, {
                            ...a,
                            literal: { ...a.literal, value: e.target.value },
                          })
                        }
                      />
                    )}
                  </>
                )}
                {a.type === "valueset" && (
                  <>
                    <input
                      data-testid="builder-cond-path"
                      value={a.path}
                      onChange={(e) => patchAtom(i, { ...a, path: e.target.value })}
                    />
                    <span className="eb-in">in</span>
                    <input
                      data-testid="builder-cond-valueset"
                      list="builder-vs-list"
                      value={a.valueset}
                      onChange={(e) =>
                        patchAtom(i, { ...a, valueset: e.target.value })
                      }
                    />
                  </>
                )}
                {a.type === "custom" && (
                  <input
                    className="eb-custom"
                    data-testid="builder-cond-custom"
                    title="outside the builder grammar — kept verbatim"
                    value={a.text}
                    onChange={(e) => patchAtom(i, { type: "custom", text: e.target.value })}
                  />
                )}
                <button
                  type="button"
                  className="eb-remove"
                  data-testid="builder-cond-remove"
                  title="remove predicate"
                  onClick={() =>
                    patch({ where: expr.where.filter((_, j) => j !== i) })
                  }
                >
                  ×
                </button>
              </div>
            ))}
            <div className="eb-row">
              <button
                type="button"
                data-testid="builder-add-cond"
                onClick={() => {
                  setDirty(true);
                  setResult(null);
                  setExpr((e) =>
                    e
                      ? {
                          ...e,
                          where: [
                            ...e.where,
                            {
                              type: "compare",
                              path: `${e.retrieve?.alias ?? "P"}.`,
                              op: "=",
                              literal: { kind: "string", value: "" },
                            },
                          ],
                        }
                      : e,
                  );
                }}
              >
                + predicate
              </button>
              <button
                type="button"
                data-testid="builder-add-custom"
                title="add a free-text predicate"
                onClick={() => {
                  setDirty(true);
                  setResult(null);
                  setExpr((e) =>
                    e ? { ...e, where: [...e.where, { type: "custom", text: "" }] } : e,
                  );
                }}
              >
                + text predicate
              </button>
            </div>
          </div>
        </div>
      )}

      <pre className="builder-pre" data-testid="builder-preview">
        {preview}
      </pre>
      <div className="eb-actions">
        <button
          type="button"
          data-testid="builder-apply"
          onClick={apply}
          disabled={!expr.name.trim() || (expr.kind === "custom" && !expr.raw.trim())}
        >
          Apply to library
        </button>
      </div>
      {result && (
        <div
          className={`diag-row ${result.ok ? "diag-info" : "diag-error"}`}
          data-testid={result.ok ? "builder-applied" : "builder-error"}
        >
          {result.detail}
        </div>
      )}
    </section>
  );
}

function blankExpr(): BuilderExpr {
  return {
    name: "",
    kind: "exists",
    retrieve: { resourceType: "Patient", alias: "P" },
    // HEDIS retrieves almost always carry a where — seed one row.
    where: [
      { type: "compare", path: "P.", op: "=", literal: { kind: "string", value: "" } },
    ],
    raw: "",
  };
}
