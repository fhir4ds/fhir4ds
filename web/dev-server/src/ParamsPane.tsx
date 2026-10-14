import { useCallback, useEffect, useState } from "react";
import type { HttpTransport } from "./http-transport";
import type { LibraryHeaderInfo } from "./transport";

/**
 * Library header / Parameters editor (v3 Slice 1). The library name is
 * read-only; parameters are added/updated/deleted through stateless server
 * transforms — the client threads the returned text through sequential
 * calls and adopts it into the shared buffer (Apply doctrine).
 */
export function ParamsPane({
  transport,
  library,
  onText,
}: {
  transport: HttpTransport;
  library: string;
  /** Adopt the transformed library text into the shared editor buffer. */
  onText: (text: string) => void;
}) {
  const [info, setInfo] = useState<LibraryHeaderInfo | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [newName, setNewName] = useState("");
  const [newType, setNewType] = useState("Integer");
  const [newDefault, setNewDefault] = useState("");
  const [showAdd, setShowAdd] = useState(false);
  const [drafts, setDrafts] = useState<Record<string, { type: string; dflt: string }>>({});

  const reload = useCallback(async () => {
    setError(null);
    try {
      setInfo(await transport.libraryHeader(library));
    } catch (e) {
      setInfo(null);
      setError(e instanceof Error ? e.message : String(e));
    }
  }, [transport, library]);

  useEffect(() => {
    reload().catch(() => {});
  }, [reload]);

  const edit = useCallback(
    async (action: "upsert" | "delete", name: string, type?: string, default_?: string) => {
      setBusy(true);
      setError(null);
      try {
        // Thread the previous result's text through sequential edits —
        // the transform is stateless server-side.
        const r = await transport.parameters(
          library,
          action,
          name,
          type,
          default_ === "" ? null : default_,
        );
        onText(r.text);
        setInfo((prev) =>
          prev ? { ...prev, parameters: r.parameters } : prev,
        );
      } catch (e) {
        setError(e instanceof Error ? e.message : String(e));
      } finally {
        setBusy(false);
      }
    },
    [transport, library, onText],
  );

  const types = [
    "Any",
    "Boolean",
    "Code",
    "Concept",
    "Date",
    "DateTime",
    "Decimal",
    "Integer",
    "Interval<Date>",
    "Interval<DateTime>",
    "Interval<Decimal>",
    "Interval<Integer>",
    "Interval<Quantity>",
    "List<Code>",
    "List<Concept>",
    "List<Decimal>",
    "List<Integer>",
    "List<Quantity>",
    "List<String>",
    "Long",
    "Quantity",
    "Ratio",
    "String",
    "Time",
  ];

  /**
   * Lenient default-field validation against the declared type. Returns an
   * advisory problem string (red hint) — the author may still save; the
   * engine surfaces hard errors at translate time.
   */
  function defaultProblem(type: string, dflt: string): string | null {
    if (dflt === "") return null;
    switch (type) {
      case "Integer":
      case "Long":
        return /^[+-]?\d+$/.test(dflt) ? null : `${type} default must be an integer literal`;
      case "Decimal":
        return /^[+-]?(\d+(\.\d+)?|\.\d+)$/.test(dflt) ? null : "Decimal default must be numeric";
      case "Boolean":
        return /^(true|false)$/.test(dflt) ? null : "Boolean default must be true or false";
      case "Date":
        return dflt.startsWith("@") ? null : "Date default is usually an @-literal (e.g. @2024-01-01)";
      case "DateTime":
        return dflt.startsWith("@") ? null : "DateTime default is usually an @-literal (e.g. @2024-01-01T10:00:00)";
      case "Time":
        return dflt.startsWith("@T") ? null : "Time default is usually an @T-literal (e.g. @T10:30:00)";
      case "Quantity":
        return /^\d+(\.\d+)?\s+('([^']+)'\s*\S+|\S+)/.test(dflt) ? null : "Quantity default looks like: 5 'mg' or 5 mg";
      case "String":
        return dflt.startsWith("'") ? null : "String default is usually single-quoted (e.g. 'male')";
      case "Interval<Integer>":
      case "Interval<Decimal>":
      case "Interval<Date>":
      case "Interval<DateTime>":
        return dflt.startsWith("Interval[") ? null : "Interval default looks like: Interval[1, 10]";
      default:
        return null;
    }
  }

  const newDefaultProblem = defaultProblem(newType, newDefault);

  return (
    <div className="dev-paramspane">
      <div className="dev-toolbar">
        <span className="dev-pane-label">Library header</span>
        <span className="dev-paramslib" title="The library name is part of the file identity — edit it in the editor">
          library {info?.library ?? library} <em>(read-only here)</em>
        </span>
      </div>
      {error && <div className="dev-vserror">{error}</div>}
      <table className="dev-paramstable">
        <thead>
          <tr>
            <th>name</th>
            <th>type</th>
            <th>default</th>
            <th title="How the parameter is referenced in CQL expressions">%ref</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {(info?.parameters ?? []).map((p) => {
            const draft = drafts[p.name] ?? { type: p.type, dflt: p.default ?? "" };
            const setDraft = (d: { type: string; dflt: string }) =>
              setDrafts((prev) => ({ ...prev, [p.name]: d }));
            const dirty = draft.type !== p.type || draft.dflt !== (p.default ?? "");
            const problem = defaultProblem(draft.type, draft.dflt);
            return (
              <tr key={p.name} className="dev-paramsrow">
                <td title="Renaming is delete + re-add in CQL semantics">
                  {p.name}
                </td>
                <td>
                  <select
                    value={draft.type}
                    title="Change the declared type"
                    onChange={(e) => setDraft({ ...draft, type: e.target.value })}
                  >
                    {types.map((t) => (
                      <option key={t} value={t}>
                        {t}
                      </option>
                    ))}
                  </select>
                </td>
                <td>
                  <input
                    className={problem ? "invalid" : undefined}
                    title={problem ?? "Default value expression (raw CQL)"}
                    value={draft.dflt}
                    placeholder="—"
                    onChange={(e) => setDraft({ ...draft, dflt: e.target.value })}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" && dirty && !problem) {
                        edit("upsert", p.name, draft.type, draft.dflt);
                      }
                    }}
                    onBlur={() => {
                      if (dirty && !problem) {
                        edit("upsert", p.name, draft.type, draft.dflt);
                      }
                    }}
                  />
                  {problem && (
                    <span className="dev-paramsadd-problem" title={problem}>
                      ⚠ {problem}
                    </span>
                  )}
                </td>
                <td>
                  <code>%{p.name}</code>
                </td>
                <td>
                  {dirty && !problem && (
                    <button
                      disabled={busy}
                      title="Apply the edited declaration"
                      onClick={() => edit("upsert", p.name, draft.type, draft.dflt)}
                    >
                      save
                    </button>
                  )}{" "}
                  <button
                    disabled={busy}
                    title="Delete this parameter declaration"
                    onClick={() => {
                      setDrafts((prev) => {
                        const next = { ...prev };
                        delete next[p.name];
                        return next;
                      });
                      edit("delete", p.name);
                    }}
                  >
                    ✕
                  </button>
                </td>
              </tr>
            );
          })}
          {(info?.parameters ?? []).length === 0 && (
            <tr>
              <td colSpan={5} className="dev-vsempty">
                No parameters declared.
              </td>
            </tr>
          )}
        </tbody>
      </table>
      <div className="dev-paramsnote">
        The header box above is read-only while this table is open — every edit
        here rewrites it. Reference parameters in expressions as{" "}
        <code>%Name</code>.
      </div>
      <div className="dev-paramsaddrow">
        <button
          className="dev-paramsaddbtn"
          disabled={busy}
          title="Add a parameter declaration row"
          onClick={() => {
            setShowAdd((v) => !v);
            setNewName("");
            setNewType("Integer");
            setNewDefault("");
          }}
        >
          {showAdd ? "▾" : "▸"} + parameter
        </button>
      </div>
      {showAdd && (
        <div className="dev-paramsadd">
          <input
            placeholder="Name"
            value={newName}
            onChange={(e) => setNewName(e.target.value)}
          />
          <select value={newType} onChange={(e) => setNewType(e.target.value)}>
            {types.map((t) => (
              <option key={t} value={t}>
                {t}
              </option>
            ))}
          </select>
          <input
            placeholder="default (optional, raw CQL)"
            className={newDefaultProblem ? "invalid" : undefined}
            title={newDefaultProblem ?? "Default value expression (raw CQL)"}
            value={newDefault}
            onChange={(e) => setNewDefault(e.target.value)}
          />
          {newDefaultProblem && (
            <span className="dev-paramsadd-problem" title={newDefaultProblem}>
              ⚠ {newDefaultProblem}
            </span>
          )}
          <button
            disabled={busy || !/^[A-Za-z][A-Za-z0-9_]*$/.test(newName)}
            title="Add or update the parameter declaration in the header"
            onClick={() => {
              edit("upsert", newName, newType, newDefault);
              setNewName("");
              setNewDefault("");
              setShowAdd(false);
            }}
          >
            add
          </button>
        </div>
      )}
    </div>
  );
}
