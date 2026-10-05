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

  const types = ["Integer", "Decimal", "String", "Boolean", "Date", "DateTime", "Time", "Quantity", "Concept", "Code", "Ratio", "Interval<Integer>"];

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
            <th />
          </tr>
        </thead>
        <tbody>
          {(info?.parameters ?? []).map((p) => (
            <tr key={p.name}>
              <td>{p.name}</td>
              <td>{p.type}</td>
              <td>{p.default ?? "—"}</td>
              <td>
                <button
                  disabled={busy}
                  title="Delete this parameter declaration"
                  onClick={() => edit("delete", p.name)}
                >
                  ✕
                </button>
              </td>
            </tr>
          ))}
          {(info?.parameters ?? []).length === 0 && (
            <tr>
              <td colSpan={4} className="dev-vsempty">
                No parameters declared.
              </td>
            </tr>
          )}
        </tbody>
      </table>
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
          value={newDefault}
          onChange={(e) => setNewDefault(e.target.value)}
        />
        <button
          disabled={busy || !/^[A-Za-z][A-Za-z0-9_]*$/.test(newName)}
          title="Add or update the parameter declaration in the header"
          onClick={() => {
            edit("upsert", newName, newType, newDefault);
            setNewName("");
            setNewDefault("");
          }}
        >
          + parameter
        </button>
      </div>
    </div>
  );
}
