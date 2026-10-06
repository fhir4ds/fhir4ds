import { useEffect, useMemo, useState } from "react";
import Editor from "@monaco-editor/react";
import { defineDevTheme } from "./boxes";
import { ResultsTable } from "@wasm-demo/components/ResultsTable";
import type { QueryResult } from "@wasm-demo/components/ResultsTable";
import { SQLOutput } from "@wasm-demo/components/SQLOutput";
import type { Transport, Diagnostic, ViewRunResult, SchemaTreeNode } from "./transport";

interface Props {
  transport: Transport;
  path: string;
  datasetName: string | null;
  patientCount: number | null;
  /** v4.3: last measure run's MeasureReports (VD-over-measure-output). */
  lastMeasureReports: Record<string, unknown>[] | null;
}

interface ConstantRow {
  name: string;
  kind: "string" | "integer" | "decimal" | "boolean" | "date" | "dateTime";
  value: string;
}

const KIND_VALUE_KEY: Record<ConstantRow["kind"], string> = {
  string: "valueString",
  integer: "valueInteger",
  decimal: "valueDecimal",
  boolean: "valueBoolean",
  date: "valueDate",
  dateTime: "valueDateTime",
};

function typedValue(kind: ConstantRow["kind"], raw: string): unknown {
  switch (kind) {
    case "integer":
    case "decimal":
      return Number(raw);
    case "boolean":
      return raw === "true";
    default:
      return raw;
  }
}

function constantsToRows(vd: Record<string, unknown>): ConstantRow[] {
  const out: ConstantRow[] = [];
  const arr = vd["constant"];
  if (Array.isArray(arr)) {
    for (const c of arr) {
      if (c && typeof c === "object") {
        const item = c as Record<string, unknown>;
        const name = typeof item["name"] === "string" ? item["name"] : "";
        const entry = Object.entries(item).find(([k, v]) => k.startsWith("value") && v !== null && v !== undefined);
        const valueKey = entry ? entry[0] : "valueString";
        const kind = (Object.entries(KIND_VALUE_KEY).find(([, k]) => k === valueKey)?.[0] ?? "string") as ConstantRow["kind"];
        out.push({ name, kind, value: entry ? String(entry[1]) : "" });
      }
    }
  }
  return out;
}

function rowsToConstants(rows: ConstantRow[]): Record<string, unknown>[] {
  return rows
    .filter((r) => r.name && r.value !== "")
    .map((r) => ({ name: r.name, [KIND_VALUE_KEY[r.kind]]: typedValue(r.kind, r.value) }));
}

/** Walk the schema tree collecting dotted paths of primitives (depth-capped). */
function collectPaths(node: SchemaTreeNode, prefix: string, out: string[], depth: number): void {
  if (depth <= 0 || !node.children) return;
  for (const c of node.children) {
    if (c.hatch) continue;
    const p = prefix ? `${prefix}.${c.name}` : c.name;
    if (c.children && c.children.length > 0 && !c.hatch) {
      out.push(p);
      collectPaths(c, p, out, depth - 1);
    } else {
      out.push(p);
    }
  }
}

export function VdPane({ transport, path, datasetName, patientCount, lastMeasureReports }: Props) {
  const stem = useMemo(() => path.split("/").pop()?.replace(/\.json$/, "") ?? path, [path]);
  const [text, setText] = useState("");
  const [dirty, setDirty] = useState(false);
  const [resource, setResource] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<ViewRunResult | null>(null);
  const [tab, setTab] = useState<"results" | "sql">("results");
  const [runError, setRunError] = useState<string | null>(null);

  // v4.3 affordances
  const [runAgainst, setRunAgainst] = useState<"dataset" | "measure">("dataset");
  const [constants, setConstants] = useState<ConstantRow[]>([]);
  const [pathAssist, setPathAssist] = useState(false);
  const [pathOptions, setPathOptions] = useState<string[] | null>(null);
  const [pathFilter, setPathFilter] = useState("");

  useEffect(() => {
    let alive = true;
    setDirty(false);
    setResult(null);
    setRunError(null);
    setError(null);
    transport
      .view(path)
      .then((v) => {
        if (!alive) return;
        setText(v.text);
        setResource(v.resource);
        try {
          setConstants(constantsToRows(JSON.parse(v.text) as Record<string, unknown>));
        } catch {
          setConstants([]);
        }
      })
      .catch((e: unknown) => alive && setError(String(e instanceof Error ? e.message : e)));
    return () => {
      alive = false;
    };
  }, [transport, path]);

  /** Rewrite the VD's constant array from the editor rows, keeping the rest of the JSON intact. */
  const applyConstants = (rows: ConstantRow[]) => {
    setConstants(rows);
    try {
      const vd = JSON.parse(text) as Record<string, unknown>;
      const consts = rowsToConstants(rows);
      if (consts.length > 0) vd["constant"] = consts;
      else delete vd["constant"];
      const next = JSON.stringify(vd, null, 2);
      setText(next);
      setDirty(true);
    } catch {
      // malformed buffer — the constants rows still hold the intent; JSON stays untouched
    }
  };

  const loadPathOptions = () => {
    if (!resource) return;
    transport
      .schemaTree(resource, 2)
      .then((t) => {
        const out: string[] = [];
        if (t.root) collectPaths(t.root, "", out, 2);
        setPathOptions(out);
      })
      .catch(() => setPathOptions([]));
  };

  const run = async () => {
    setBusy(true);
    setRunError(null);
    setResult(null);
    try {
      const r =
        runAgainst === "measure" && lastMeasureReports && lastMeasureReports.length > 0
          ? await transport.viewRun(text, undefined, lastMeasureReports)
          : await transport.viewRun(text, undefined);
      if (r.ok) {
        setResult(r);
        setTab("results");
      } else {
        const d = (r.diagnostics as Diagnostic[] | undefined)?.[0];
        setRunError(d?.message ?? "view run failed");
      }
    } catch (e: unknown) {
      setRunError(String(e instanceof Error ? e.message : e));
    } finally {
      setBusy(false);
    }
  };

  const filteredPaths = useMemo(() => {
    if (!pathOptions) return [];
    const f = pathFilter.trim().toLowerCase();
    return (f ? pathOptions.filter((p) => p.toLowerCase().includes(f)) : pathOptions).slice(0, 40);
  }, [pathOptions, pathFilter]);

  return (
    <div className="dev-vdpane">
      <div className="dev-vdhead">
        <strong>ViewDefinition: {stem}</strong>
        {resource ? <span className="dev-vdres"> · resource {resource}</span> : null}
        {runAgainst === "measure" ? (
          <span className="dev-vdctx"> · run against last measure output{lastMeasureReports ? ` (${lastMeasureReports.length} MeasureReports)` : " (none yet — run a measure first)"}</span>
        ) : datasetName ? (
          <span className="dev-vdctx"> · dataset {datasetName}{patientCount !== null ? ` (${patientCount} patients)` : ""}</span>
        ) : null}
      </div>
      <div className="dev-vdbar">
        <button
          className="dev-vdrun"
          onClick={run}
          disabled={busy || dirty || (runAgainst === "measure" && (!lastMeasureReports || lastMeasureReports.length === 0))}
          title={
            dirty
              ? "Apply edits first (editors are the writer; the file is the source)"
              : runAgainst === "measure"
                ? "Stage the last measure run's MeasureReports as the view input (resource must be MeasureReport)"
                : "Run this view over the loaded dataset"
          }
        >
          ▶ Run view
        </button>
        <select
          className="dev-vdagainst"
          value={runAgainst}
          onChange={(e) => setRunAgainst(e.target.value as "dataset" | "measure")}
          title="Choose what the view runs over"
        >
          <option value="dataset">Run against: dataset</option>
          <option value="measure">Run against: last measure output</option>
        </select>
        <button
          className="dev-vdpathbtn"
          onClick={() => {
            const next = !pathAssist;
            setPathAssist(next);
            if (next && pathOptions === null) loadPathOptions();
          }}
          title="Schema-aware path suggestions for this view's resource"
        >
          {pathAssist ? "▾ path assist" : "▸ path assist"}
        </button>
        {dirty ? <span className="dev-vddirty">buffer edited — file preview only; Save writes are not part of v1</span> : null}
      </div>
      {pathAssist ? (
        <div className="dev-vdpaths">
          <input
            className="dev-vdpathfilter"
            placeholder={`filter ${resource ?? ""} paths…`}
            value={pathFilter}
            onChange={(e) => setPathFilter(e.target.value)}
          />
          {pathOptions === null ? (
            <span className="dev-vdpathnote">loading schema…</span>
          ) : (
            <div className="dev-vdpathlist">
              {filteredPaths.map((p) => (
                <code key={p} className="dev-vdpathitem" title="Copy into a column path / where expression">
                  {p}
                </code>
              ))}
              {filteredPaths.length === 0 ? <span className="dev-vdpathnote">no matching paths</span> : null}
            </div>
          )}
          <span className="dev-vdpathnote">paths are relative to the current focus — prefix %resource for the row resource, %context for the current node.</span>
        </div>
      ) : null}
      {error ? <div className="dev-vderror">{error}</div> : null}
      <div className="dev-vdeditor">
        <Editor
          height="220px"
          theme="dev-cql"
          defaultLanguage="json"
          value={text}
          onMount={(_, monaco) => defineDevTheme(monaco)}
          onChange={(v) => {
            setText(v ?? "");
            setDirty(true);
          }}
          options={{ minimap: { enabled: false }, lineNumbers: "on", scrollBeyondLastLine: false, tabSize: 2 }}
        />
      </div>
      <div className="dev-vdconsts">
        <div className="dev-vdconsts-head">
          constants <span>(top-level `constant` array — referenced as %name in paths; the table is the writer)</span>
        </div>
        <div className="dev-vdconst-rows">
          {constants.map((row, i) => (
            <div className="dev-vdconst-row" key={i}>
              <input
                className="dev-vdconst-name"
                placeholder="name"
                value={row.name}
                onChange={(e) => {
                  const rows = constants.map((r, j) => (j === i ? { ...r, name: e.target.value } : r));
                  applyConstants(rows);
                }}
              />
              <select
                className="dev-vdconst-kind"
                value={row.kind}
                onChange={(e) => {
                  const rows = constants.map((r, j) => (j === i ? { ...r, kind: e.target.value as ConstantRow["kind"] } : r));
                  applyConstants(rows);
                }}
              >
                {(Object.keys(KIND_VALUE_KEY) as ConstantRow["kind"][]).map((k) => (
                  <option key={k} value={k}>
                    {k}
                  </option>
                ))}
              </select>
              <input
                className="dev-vdconst-value"
                placeholder="value"
                value={row.value}
                onChange={(e) => {
                  const rows = constants.map((r, j) => (j === i ? { ...r, value: e.target.value } : r));
                  applyConstants(rows);
                }}
              />
              <button
                className="dev-vdconst-del"
                title="Remove constant"
                onClick={() => applyConstants(constants.filter((_, j) => j !== i))}
              >
                ✕
              </button>
            </div>
          ))}
        </div>
        <button
          className="dev-vdconst-add"
          onClick={() => applyConstants([...constants, { name: "", kind: "string", value: "" }])}
        >
          + constant
        </button>
      </div>
      <div className="dev-vdhint">
        where paths evaluate against the iterated focus — use %resource for the row resource, %context for the current node.
      </div>
      {runError ? (
        <div className="dev-vderror" role="alert">
          {runError}
        </div>
      ) : null}
      {result ? (
        <div className="dev-vdresults">
          <div className="dev-vdtabs">
            <button className={tab === "results" ? "on" : ""} onClick={() => setTab("results")}>
              Results ({result.rows.length} rows)
            </button>
            <button className={tab === "sql" ? "on" : ""} onClick={() => setTab("sql")}>
              SQL
            </button>
            <span className="dev-vdcount">{result.resource_count} {result.resource_count === 1 ? "resource" : "resources"} staged</span>
          </div>
          {tab === "results" ? (
            <ResultsTable
              result={{ columns: result.columns, rows: result.rows.map((r) => result.columns.map((c) => r[c])), rowCount: result.rows.length, executionTimeMs: 0 } satisfies QueryResult}
              error={null}
              isLoading={false}
            />
          ) : (
            <SQLOutput value={result.sql} />
          )}
        </div>
      ) : null}
    </div>
  );
}
