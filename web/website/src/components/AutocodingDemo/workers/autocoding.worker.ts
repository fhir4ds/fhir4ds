/**
 * Pyodide Web Worker: runs the REAL fhir4ds AutoCoder in the browser.
 *
 * fhir4ds-v2 is installed via micropip from the wheel served under
 * /bulk-publisher-app/ (same discovery scheme as the bulk-publish demo).
 *
 * The terminology endpoint subclasses the wheel's own
 * HTTPTerminologyEndpoint — only the network call is overridden with a
 * synchronous XHR (legal inside a worker; httpx cannot run under Pyodide).
 * URL validation, the circuit breaker, search_batch fan-out and ALL
 * $search → SearchResult parsing remain the package's real code. The
 * AutoCoder itself (detection, cache/filter policy, Coding construction,
 * audit extension) is the shipped implementation, unmodified.
 */

interface WorkerMessage {
  id: number;
  type: 'init' | 'autocode';
  resource?: string; // JSON-stringified FHIR resource
  minGrade?: string;
  topK?: number;
  mode?: string;
}

interface WorkerReply {
  id: number;
  ok: boolean;
  error?: string;
  augmented?: string; // JSON-stringified augmented resource
  rows?: string; // JSON-stringified search rows captured during the run
  query?: string;
  category?: string;
}

const PYODIDE_CDN = 'https://cdn.jsdelivr.net/pyodide/v0.27.7/full/';
const TERMINOLOGY_BASE =
  'https://fhir4ds-terminology-demo-server.hf.space/fhir';
const FHIR4DS_WHEEL_FALLBACK = 'fhir4ds_v2-0.0.23-py3-none-any.whl';

function getAssetBase(): string {
  return `${self.location.origin}/bulk-publisher-app`;
}

async function findWheelUrl(): Promise<string> {
  const base = getAssetBase();
  try {
    const res = await fetch(`${base}/`);
    if (res.ok) {
      const html = await res.text();
      const matches = [
        ...html.matchAll(/href="([^"]*fhir4ds_v2-[^"]*-py3-none-any\.whl)"/g),
      ];
      if (matches.length > 0) {
        // Directory listings may HTML-escape slashes (&#47;); split on
        // both so the bare filename is extracted either way.
        const name = matches[matches.length - 1][1]
          .split(/\/|&#47;/)
          .pop()!;
        return `${base}/${name}`;
      }
    }
  } catch {
    // fall through to fallback
  }
  return `${base}/${FHIR4DS_WHEEL_FALLBACK}`;
}

const PYTHON_SETUP = `
import json
import logging
import types as _types

# The Pyodide-hosted duckdb package lacks 'sqltypes' (a CPython-package-only
# module used by UDF registration). The AutoCoder path never registers UDFs,
# so a inert namespace satisfies the transitive import in cql.duckdb.udf.
import duckdb as _duckdb
if not hasattr(_duckdb, "sqltypes"):
    class _SqlTypesStub(_types.ModuleType):
        def __getattr__(self, name):
            return None
    _duckdb.sqltypes = _SqlTypesStub("sqltypes")

from fhir4ds.cql.terminology.http_adapter import HTTPTerminologyEndpoint
from fhir4ds.cql.terminology.system_mappings import category_to_system_param

class WorkerTerminologyEndpoint(HTTPTerminologyEndpoint):
    """HTTPTerminologyEndpoint with the HTTP call swapped for a sync XHR
    bridged to JS. Parsing, validation and the breaker are inherited."""
    def search_text(self, query, category, *, mode="hybrid"):
        now = __import__("time").monotonic()
        if self._is_breaker_open(now):
            return []
        try:
            raw = __ts_search__(query, category, mode)
            payload = json.loads(raw)
            result = self._search_payload_to_results(payload, mode=mode)
            self._on_call_success()
            return result
        except Exception:
            self._on_call_failure()
            raise

_captured_rows = []
_captured_query = None
_captured_category = None
_logbuf = __import__("io").StringIO()
_handler = __import__("logging").StreamHandler(_logbuf)
_handler.setFormatter(__import__("logging").Formatter("%(name)s: %(message)s"))
logging.getLogger("fhir4ds").addHandler(_handler)
logging.getLogger("fhir4ds").setLevel(logging.DEBUG)

def run_autocode(resource_json, min_grade, top_k, search_mode):
    global _captured_rows, _captured_query, _captured_category
    from fhir4ds.cql.loader import AutoCoder, AutoCoderConfig

    resource = json.loads(resource_json)
    endpoint = WorkerTerminologyEndpoint(${JSON.stringify(TERMINOLOGY_BASE)}, timeout_seconds=60.0)

    real_search = endpoint.search_text
    def capturing(query, category, *, mode="hybrid"):
        global _captured_query, _captured_category
        _captured_query, _captured_category = query, category
        results = real_search(query, category, mode=mode)
        # 0.0.22: the wheel's AutoCoder accepts SearchResult dataclasses
        # directly (_result_to_dict handles both shapes) — no dict
        # conversion here (AMUX-62 workaround removed).
        _captured_rows[:] = [
            {k: getattr(r, k, None) for k in ("code", "system", "display", "score", "match_grade")}
            for r in results
        ]
        return results
    endpoint.search_text = capturing

    coder = AutoCoder(endpoint, None,
                      config=AutoCoderConfig(min_match_grade=min_grade, top_k=top_k,
                                             search_mode=search_mode))
    coder.augment_resource(resource)
    return json.dumps({"resource": resource, "logs": _logbuf.getvalue()[-3000:]})
`;

let pyodide: any = null;

const memo = new Map<string, string>();

// Synchronous XHR bridge (workers permit sync XHR).
function tsSearch(query: string, category: string, mode: string): string {
  const key = `${query}\u0000${category}\u0000${mode}`;
  const cached = memo.get(key);
  if (cached !== undefined) return cached;
  const params = new URLSearchParams({
    query,
    searchMode: mode,
    count: '25',
  });
  const system = categoryToSystem(category);
  if (system) params.set('system', system);
  const xhr = new XMLHttpRequest();
  xhr.open(
    'GET',
    `${TERMINOLOGY_BASE}/CodeSystem/$search?${params.toString()}`,
    false, // synchronous — the python caller is sync
  );
  xhr.timeout = 60000;
  xhr.send(null);
  if (xhr.status === 503) {
    throw new Error(
      'WAKING: the terminology engine is waking up — retry in ~30s',
    );
  }
  if (xhr.status === 429) {
    throw new Error('RATE_LIMITED: demo rate limit (30/min) — wait a moment');
  }
  if (xhr.status !== 200) {
    throw new Error(`terminology search failed: HTTP ${xhr.status}`);
  }
  const body = xhr.responseText;
  if (memo.size < 200) memo.set(key, body);
  return body;
}

// Best-effort warm-up: primes the terminology engine after Space idle so
// the first real search doesn't also pay the model-load latency.
function warm(): void {
  try {
    const xhr = new XMLHttpRequest();
    xhr.open(
      'GET',
      `${TERMINOLOGY_BASE}/CodeSystem/$search?query=diabetes&searchMode=lexical&count=1`,
      true,
    );
    xhr.send(null);
  } catch {
    // best-effort only
  }
}

// Mirrors the package's category→system mapping for the URL we build on
// the JS side (the python side validates the same inputs).
function categoryToSystem(category: string): string {
  const map: Record<string, string> = {
    condition: 'http://snomed.info/sct',
    medication: 'http://www.nlm.nih.gov/research/umls/rxnorm',
    procedure: 'http://snomed.info/sct',
    observation: 'http://loinc.org',
  };
  return map[category] ?? '';
}

self.onmessage = async (e: MessageEvent<WorkerMessage>) => {
  const {id, type} = e.data;
  const reply = (r: WorkerReply) => (self as any).postMessage(r);
  try {
    if (type === 'init') {
      if (!pyodide) {
        const {loadPyodide} = await import(/* webpackIgnore: true */ `${PYODIDE_CDN}pyodide.mjs`);
        pyodide = await loadPyodide({indexURL: PYODIDE_CDN});
        await pyodide.loadPackage(['micropip', 'duckdb', 'orjson', 'pyarrow']);
        const wheelUrl = await findWheelUrl();
        pyodide.globals.set('__wheel_url__', wheelUrl);
        pyodide.globals.set('__ts_search__', tsSearch);
        await pyodide.runPythonAsync(`
import micropip
await micropip.install(["antlr4-python3-runtime>=4.10", "python-dateutil>=2.8"])
await micropip.install(__wheel_url__, deps=False)
`);
        await pyodide.runPythonAsync(PYTHON_SETUP);
      }
      warm();
      reply({id, ok: true});
      return;
    }
    if (type === 'autocode') {
      pyodide.globals.set('_resource_json', e.data.resource!);
      pyodide.globals.set('_min_grade', e.data.minGrade!);
      pyodide.globals.set('_top_k', e.data.topK ?? 3);
      pyodide.globals.set('_search_mode', e.data.mode ?? 'semantic');
      const result = await pyodide.runPythonAsync(`
import traceback
_error = None
_payload = None
try:
    _payload = run_autocode(_resource_json, _min_grade, int(_top_k), _search_mode)
except Exception as ex:
    _error = f"{type(ex).__name__}: {ex}"
[_payload, _error, _captured_rows, _captured_query, _captured_category]
`);
      const [payload, error, rows, query, category] = result.toJs
        ? result.toJs()
        : result;
      if (error) throw new Error(String(error));
      const parsed = JSON.parse(String(payload));
      reply({
        id,
        ok: true,
        augmented: JSON.stringify(parsed.resource),
        logs: parsed.logs ?? '',
        rows: JSON.stringify(Array.from(rows ?? [])),
        query: query ? String(query) : undefined,
        category: category ? String(category) : undefined,
      });
    }
  } catch (err) {
    reply({id, ok: false, error: String((err as Error).message)});
  }
};

export {};
