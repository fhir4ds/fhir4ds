// Pyodide Web Worker: loads fhir4ds-v2 and provides ViewDefinition → SQL
// translation via fhir4ds.generate_view_sql().
//
// fhir4ds-v2 is a pure Python package (zero C/WASM deps) installed via
// micropip from a wheel served from /bulk-publisher-app/.

interface WorkerMessage {
  id: number;
  type: "init" | "translate";
  viewDefinition?: string; // JSON-stringified ViewDefinition
}

const PYODIDE_CDN = "https://cdn.jsdelivr.net/pyodide/v0.27.7/full/";

// Hardcoded for the Docusaurus embed. In the standalone Vite demo this was
// injected via `define` after globbing public/; here we ship exactly one
// wheel under static/bulk-publisher-app/ so the name is a constant.
const FHIR4DS_WHEEL_NAME = "fhir4ds_v2-0.0.10-py3-none-any.whl";

// Workers don't see the page's window.location; use self.location.origin +
// the known static path. Matches lib/asset-base.ts.
function getAssetBase(): string {
  return `${self.location.origin}/bulk-publisher-app`;
}

let pyodide: any = null;

self.onmessage = async (e: MessageEvent<WorkerMessage>) => {
  const { id, type, viewDefinition } = e.data;

  if (type === "init") {
    try {
      await initPyodide();
      self.postMessage({ id: 0, ok: true });
    } catch (err) {
      const stack = err instanceof Error ? `${err.message}\n${err.stack ?? ""}` : String(err);
      self.postMessage({
        id: 0,
        ok: false,
        error: stack,
      });
    }
    return;
  }

  if (type === "translate") {
    const start = performance.now();
    try {
      if (!pyodide) throw new Error("Pyodide not initialized");
      const sql = await translateViewDef(viewDefinition ?? "");
      const timeMs = performance.now() - start;
      self.postMessage({ id, ok: true, sql, timeMs });
    } catch (err) {
      self.postMessage({
        id,
        ok: false,
        error: err instanceof Error ? err.message : String(err),
      });
    }
  }
};

async function initPyodide() {
  // `webpackIgnore: true` tells Webpack/Rspack not to try to bundle this
  // dynamic import. The URL is fetched at runtime from the Pyodide CDN.
  // (Vite equivalent was `@vite-ignore`.)
  const { loadPyodide } = await import(/* webpackIgnore: true */ `${PYODIDE_CDN}pyodide.mjs`);
  pyodide = await loadPyodide({ indexURL: PYODIDE_CDN });

  // Pyodide-hosted packages imported by fhir4ds at module load. The wheel is
  // installed with deps=False below, so we load these explicitly.
  await pyodide.loadPackage(["micropip", "duckdb", "orjson", "pyarrow"]);

  // Wheel is served from /bulk-publisher-app/ alongside the duckdb wasm
  // and the synthesized NDJSON data. No build-time injection needed.
  const wheelUrl = `${getAssetBase()}/${FHIR4DS_WHEEL_NAME}`;
  console.log("[Pyodide Worker] Installing fhir4ds-v2 from:", wheelUrl);

  pyodide.globals.set("__wheel_url__", wheelUrl);
  await pyodide.runPythonAsync(`
import micropip

# Pure-Python runtime deps that aren't Pyodide-hosted.
await micropip.install([
    "antlr4-python3-runtime>=4.10",
    "python-dateutil>=2.8",
])

# fhir4ds wheel itself — skip PyPI dep resolution (native deps come from
# Pyodide-hosted packages or DuckDB-WASM).
await micropip.install(__wheel_url__, deps=False)
`);

  // Smoke-test the import. generate_view_sql is the top-level convenience
  // function we rely on for ViewDefinition → SQL translation.
  pyodide.runPython(`
import fhir4ds
assert callable(fhir4ds.generate_view_sql), "fhir4ds.generate_view_sql not reachable"
print("[Pyodide Worker] fhir4ds-v2 ready; version =", fhir4ds.__version__)
`);

  console.log("[Pyodide Worker] Initialization complete");
}

async function translateViewDef(viewDefJson: string): Promise<string> {
  pyodide.globals.set("_viewdef_input", viewDefJson);

  const pyResult = pyodide.runPython(`
import traceback
import json

_error = None
_sql = None
try:
    import fhir4ds
    _vd = json.loads(_viewdef_input)
    _sql = fhir4ds.generate_view_sql(_vd)
except Exception as e:
    lines = traceback.format_exc().strip().splitlines()
    last = next(
        (l.strip() for l in reversed(lines) if l.strip() and not l.startswith("During")),
        str(e),
    )
    _error = f"{type(e).__name__}: {last.split(': ', 1)[-1]}"

[_sql, _error]
`);

  const [sql, err] = pyResult.toJs ? pyResult.toJs() : Array.from(pyResult);
  if (err) throw new Error(String(err));
  return typeof sql === "string" ? sql : String(sql);
}
