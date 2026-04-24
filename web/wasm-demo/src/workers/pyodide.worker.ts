// Pyodide Web Worker: loads fhir4ds-v2 and provides CQL → SQL translation.
// fhir4ds-v2 is a pure Python package (zero C/WASM deps) installed via micropip
// from a wheel bundled in public/.
//
// Translation pipeline:
//   1. fhir4ds.cql parses CQL and generates SQL with fhirpath_text() calls
//   2. postprocessSQL() rewrites list_extract(fhirpath_text(X,Y),N) →
//      fhirpath_text(X,Y) so nested JSON navigation works with the SQL
//      macro implementation of fhirpath_text registered in DuckDB.

declare const self: DedicatedWorkerGlobalScope;
// Injected at build/dev time by vite.config.ts via `define`.
// Resolves to the actual wheel filename (e.g. "fhir4ds_v2-0.0.2-py3-none-any.whl").
declare const __FHIR4DS_WHEEL_NAME__: string;

interface WorkerMessage {
  id: number;
  type: "init" | "translate";
  cql?: string;
  audit?: boolean;
}

const PYODIDE_CDN = "https://cdn.jsdelivr.net/pyodide/v0.27.7/full/";

let pyodide: any = null;

self.onmessage = async (e: MessageEvent<WorkerMessage>) => {
  const { id, type, cql, audit } = e.data;

  if (type === "init") {
    try {
      await initPyodide();
      self.postMessage({ id: 0, ok: true });
    } catch (err) {
      self.postMessage({ id: 0, ok: false, error: err instanceof Error ? err.message : String(err) });
    }
    return;
  }

  if (type === "translate") {
    const start = performance.now();
    try {
      if (!pyodide) throw new Error("Pyodide not initialized");
      const rawSql = await translateCQL(cql ?? "", audit ?? false);
      const sql = postprocessSQL(rawSql);
      const timeMs = performance.now() - start;
      self.postMessage({ id, ok: true, sql, timeMs });
    } catch (err) {
      self.postMessage({ id, ok: false, error: err instanceof Error ? err.message : String(err) });
    }
  }
};

async function initPyodide() {
  const { loadPyodide } = await import(/* @vite-ignore */ `${PYODIDE_CDN}pyodide.mjs`);
  pyodide = await loadPyodide({ indexURL: PYODIDE_CDN });

  // Only micropip is needed — fhir4ds-v2 is pure Python (no native deps)
  await pyodide.loadPackage(["micropip"]);
  const micropip = pyodide.pyimport("micropip");

  // Wheel filename is injected at build/dev time by vite.config.ts via `define`.
  // No runtime fetch needed — works in dev mode, build, and Docusaurus static hosting.
  // @vite-ignore prevents Vite's asset URL transformation on the .whl extension.
  const wheelUrl = new URL(/* @vite-ignore */ `./${__FHIR4DS_WHEEL_NAME__}`, import.meta.url).href;

  console.log("[Pyodide Worker] Installing fhir4ds-v2 from:", wheelUrl);
  await micropip.install(wheelUrl);

  // Smoke-test the import
  pyodide.runPython(`
from fhir4ds.cql.parser import parse_cql
from fhir4ds.cql import CQLToSQLTranslator
print("[Pyodide Worker] fhir4ds-v2 ready")
`);

  console.log("[Pyodide Worker] Initialization complete");
}

async function translateCQL(cqlText: string, audit: boolean): Promise<string> {
  pyodide.globals.set("_cql_input", cqlText);
  pyodide.globals.set("_audit_mode", audit);

  const pyResult = pyodide.runPython(`
import traceback
from fhir4ds.cql.parser import parse_cql
from fhir4ds.cql import CQLToSQLTranslator

_error = None
_sql = None
try:
    _library = parse_cql(_cql_input)
    _translator = CQLToSQLTranslator()
    if _audit_mode:
        _translator.context.set_audit_mode(True)
    _sql = _translator.translate_library_to_population_sql(_library)
except Exception as e:
    lines = traceback.format_exc().strip().splitlines()
    last = next((l.strip() for l in reversed(lines) if l.strip() and not l.startswith("During")), str(e))
    _error = f"{type(e).__name__}: {last.split(': ', 1)[-1]}"

[_sql, _error]
`);

  const [sql, err] = pyResult.toJs ? pyResult.toJs() : Array.from(pyResult);
  if (err) throw new Error(String(err));
  return typeof sql === "string" ? sql : String(sql);
}

/**
 * Post-process fhir4ds-v2 generated SQL to make it compatible with both the C++
 * fhirpath UDF (which returns JSON[]) and the SQL macro fallback (VARCHAR).
 *
 * fhir4ds-v2 wraps `.first()` as list_extract(expr, N).
 * With the C++ UDF, list_extract on a JSON[] is correct.
 * With the SQL macro fallback, list_extract on VARCHAR just extracts a char.
 * We strip list_extract wrappers whose inner expression contains a fhirpath
 * call, using a balanced-parentheses scanner for correct nesting.
 */
function postprocessSQL(sql: string): string {
  return removeListExtractFhirpathWrappers(sql);
}

function removeListExtractFhirpathWrappers(sql: string): string {
  const NEEDLE = "list_extract(";
  let result = sql;
  let changed = true;
  while (changed) {
    changed = false;
    let out = "";
    let pos = 0;
    while (pos < result.length) {
      const idx = result.indexOf(NEEDLE, pos);
      if (idx === -1) { out += result.slice(pos); break; }

      let depth = 0;
      let lastTopComma = -1;
      let i = idx + NEEDLE.length - 1; // points at opening '('
      let inStr = false;
      let qChar = "";
      for (; i < result.length; i++) {
        const c = result[i];
        if (inStr) {
          if (c === qChar && result[i - 1] !== "\\") inStr = false;
        } else if (c === "'" || c === '"') {
          inStr = true; qChar = c;
        } else if (c === "(") {
          depth++;
        } else if (c === ")") {
          depth--;
          if (depth === 0) break;
        } else if (c === "," && depth === 1) {
          lastTopComma = i;
        }
      }

      if (depth !== 0 || lastTopComma === -1) {
        out += result.slice(pos, idx + 1); pos = idx + 1; continue;
      }

      const innerExpr = result.slice(idx + NEEDLE.length, lastTopComma).trim();

      if (/fhirpath/i.test(innerExpr)) {
        // Replace list_extract(innerExpr, N) with just innerExpr
        out += result.slice(pos, idx) + innerExpr;
        result = out + result.slice(i + 1);
        changed = true;
        out = ""; pos = 0;
        continue;
      }

      out += result.slice(pos, i + 1); pos = i + 1;
    }
    if (!changed) result = out;
  }
  return result;
}

